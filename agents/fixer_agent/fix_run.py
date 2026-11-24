"""The fix run (M2-7): drives OpenHands in the sandbox, then runs the sanity check.

This runs in the client container, which can reach the sandbox over the private network and nothing else.
It holds the Anthropic key. It never holds a GitHub token.

What it does, in order:
  1. Start one OpenHands conversation in the sandbox, with a dollar cap and an iteration cap that
     OpenHands itself enforces. Sub-agents are off.
  2. Send the task and wait. An internal deadline writes the last known cost and exits if the run takes too long.
  3. Read the cost and token counts from OpenHands and write them to metrics.json (a snapshot while the run
     goes, the final figure at the end).
  4. If the agent finished, run the sanity check (agents/fixer_agent/sanity.py), with no model involved.

It writes metrics.json, events.jsonl, sanity.json and result.json to the output folder. The key is blanked
out of everything it writes.

Exit codes: 0 ready for the next step, 10 stopped (a cap or an agent error), 11 sanity check failed,
12 error, 13 deadline.
"""
import argparse
import json
import math
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from agents.fixer_agent import sanity

MODEL = "anthropic/claude-sonnet-5-5"      # pinned. Claude Sonnet 5.5, as in spike S2a
MAX_BUDGET = 1.00                          # dollars per conversation (owner decision, 2026-11-24)
MAX_ITERATIONS = 40                        # steps per conversation (same decision)
WALL_CLOCK_SECONDS = 840                   # inside the 15-minute limit the launcher puts around the whole run
SNAPSHOT_EVERY_SECONDS = 5

EXIT_READY, EXIT_STOPPED, EXIT_SANITY, EXIT_ERROR, EXIT_TIMEOUT = 0, 10, 11, 12, 13


class ConfigError(Exception):
    """A setting is missing or not allowed. The message names the setting, never the key."""


@dataclass
class Config:
    host: str
    api_key: str
    model: str
    max_budget: float
    max_iterations: int
    out_dir: str
    wall_clock: int = WALL_CLOCK_SECONDS


def config_from_env(env, out_dir):
    """Defaults are the agreed caps. They can be lowered, never raised."""
    if not env.get("ANTHROPIC_API_KEY"):
        raise ConfigError("ANTHROPIC_API_KEY is not set")
    if not env.get("AGENT_HOST"):
        raise ConfigError("AGENT_HOST is not set")
    model = env.get("MODEL", MODEL)
    if model != MODEL:
        raise ConfigError(f"the model is pinned to {MODEL}")
    try:
        budget = float(env.get("MAX_BUDGET", MAX_BUDGET))
    except ValueError:
        budget = math.nan
    if not (0 < budget <= MAX_BUDGET):
        raise ConfigError(f"MAX_BUDGET must be above 0 and at most {MAX_BUDGET}")
    try:
        iterations = int(env.get("MAX_ITER", MAX_ITERATIONS))
    except ValueError:
        iterations = 0
    if not (0 < iterations <= MAX_ITERATIONS):
        raise ConfigError(f"MAX_ITER must be a whole number from 1 to {MAX_ITERATIONS}")
    return Config(host=env["AGENT_HOST"], api_key=env["ANTHROPIC_API_KEY"], model=model,
                  max_budget=budget, max_iterations=iterations, out_dir=out_dir)


def load_sdk():  # pragma: no cover - the real SDK; every test uses a fake
    """The real OpenHands SDK, behind the few names this module uses."""
    from pydantic import SecretStr
    from openhands.sdk import LLM, Conversation
    from openhands.sdk.conversation.exceptions import ConversationRunError
    from openhands.sdk.workspace import RemoteWorkspace
    from openhands.sdk import Agent
    from openhands.tools.preset.default import get_default_condenser, get_default_tools

    def make_llm(**kw):
        kw["api_key"] = SecretStr(kw["api_key"])
        return LLM(**kw)

    def make_agent(llm):
        # Sub-agents are off on purpose, and written out: a child's budget check does not come out of
        # the parent's remaining cap (spike S2a), so turning them on would make the cap meaningless.
        return Agent(llm=llm,
                     tools=get_default_tools(enable_browser=False, enable_sub_agents=False),
                     system_prompt_kwargs={"cli_mode": True},
                     condenser=get_default_condenser(llm=llm.model_copy(update={"usage_id": "condenser"})))

    return SimpleNamespace(LLM=make_llm, make_agent=make_agent, RemoteWorkspace=RemoteWorkspace,
                           Conversation=Conversation, ConversationRunError=ConversationRunError)


def _blank(text, secrets):
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def _write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_metrics(conv):
    """(cost, tokens) from OpenHands, or (None, None) if the call fails. Never a made-up zero."""
    try:
        m = conv.conversation_stats.get_combined_metrics()
        cost = float(m.accumulated_cost)
        usage = m.accumulated_token_usage
        return cost, {
            "input_tokens": getattr(usage, "prompt_tokens", None),
            "output_tokens": getattr(usage, "completion_tokens", None),
            "cache_read_tokens": getattr(usage, "cache_read_tokens", None),
            "cache_write_tokens": getattr(usage, "cache_write_tokens", None),
        }
    except Exception:
        return None, None


def write_snapshot(conv, cfg, seconds, final, budget_cap_hit=False, iteration_cap_hit=False):
    cost, tokens = read_metrics(conv) if conv is not None else (None, None)
    data = {"model": cfg.model, "cost_usd": cost, "budget_cap_hit": budget_cap_hit,
            "iteration_cap_hit": iteration_cap_hit, "seconds": round(seconds, 1),
            "max_budget": cfg.max_budget, "max_iterations": cfg.max_iterations,
            "final": bool(final and cost is not None)}
    data.update(tokens or {"input_tokens": None, "output_tokens": None,
                           "cache_read_tokens": None, "cache_write_tokens": None})
    _write_json(Path(cfg.out_dir) / "metrics.json", data)


def _result(cfg, outcome, reason=""):
    _write_json(Path(cfg.out_dir) / "result.json", {"outcome": outcome, "reason": reason})


def on_deadline(conv, cfg, started, exit_fn=os._exit, clock=time.monotonic):
    """The run took too long. Save the last known cost, say so, and stop. Independent of the cost cap."""
    write_snapshot(conv, cfg, clock() - started, final=False)
    _result(cfg, "timeout", f"no answer within {cfg.wall_clock} seconds")
    exit_fn(EXIT_TIMEOUT)


def run(task, cfg, sdk, clock=time.monotonic):
    out = Path(cfg.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = clock()
    secrets = [cfg.api_key]
    holder = {"conv": None, "last": None}
    events = open(out / "events.jsonl", "w", encoding="utf-8")

    def on_event(event):
        events.write(_blank(event.model_dump_json(), secrets) + "\n")
        events.flush()
        now = clock()
        if holder["last"] is None or now - holder["last"] >= SNAPSHOT_EVERY_SECONDS:
            holder["last"] = now
            write_snapshot(holder["conv"], cfg, now - started, final=False)

    outcome, reason, budget_hit, iteration_hit = "ready", "", False, False
    timer = None
    try:
        llm = sdk.LLM(model=cfg.model, api_key=cfg.api_key, usage_id="fixer")
        agent = sdk.make_agent(llm)
        workspace = sdk.RemoteWorkspace(host=cfg.host, working_dir=sanity.WORKDIR)
        conv = holder["conv"] = sdk.Conversation(
            agent=agent, workspace=workspace, callbacks=[on_event],
            max_iteration_per_run=cfg.max_iterations, max_budget_per_run=cfg.max_budget)
        timer = threading.Timer(cfg.wall_clock, on_deadline, args=(conv, cfg, started))
        timer.daemon = True
        timer.start()
        conv.send_message(task["prompt"])
        conv.run()
        status = getattr(conv.state, "execution_status", None)
        if str(getattr(status, "value", status)).lower() != "finished":
            outcome, reason = "agent_error", f"the run ended with status {status}"
    except sdk.ConversationRunError as e:
        code = getattr(getattr(e, "conversation_error", None), "code", None)
        if code == "MaxBudgetReached":
            outcome, budget_hit = "budget_cap_hit", True
        elif code == "MaxIterationsReached":
            outcome, iteration_hit = "iteration_cap_hit", True
        else:
            outcome, reason = "agent_error", _blank(str(e), secrets)[:300]
    except Exception as e:
        outcome, reason = "error", _blank(f"{type(e).__name__}: {e}", secrets)[:300]
    finally:
        if timer:
            timer.cancel()
        events.close()

    conv = holder["conv"]
    write_snapshot(conv, cfg, clock() - started, final=True, budget_cap_hit=budget_hit,
                   iteration_cap_hit=iteration_hit)

    code = EXIT_READY
    if outcome == "ready":
        def execute(command, timeout):
            r = workspace.execute_command(command, timeout=timeout)
            return r.exit_code, (r.stdout or "") + (r.stderr or "")
        result = sanity.run_sanity(execute, scrub=secrets)
        _write_json(out / "sanity.json", result.as_dict())
        if not result.ok:
            outcome, reason, code = "sanity_failed", "; ".join(result.reasons), EXIT_SANITY
    elif outcome == "error":
        code = EXIT_ERROR
    else:
        code = EXIT_STOPPED
    _result(cfg, outcome, reason)
    if conv is not None:
        try:
            conv.close()
        except Exception:
            pass
    return code


def main(argv=None, env=None):
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description="Run the OpenHands fixer on one task, then the sanity check.")
    ap.add_argument("--task", required=True, help="task.json from the task step")
    ap.add_argument("--out", required=True, help="the output folder")
    args = ap.parse_args(argv)
    try:
        cfg = config_from_env(env, args.out)
        task = json.loads(Path(args.task).read_text(encoding="utf-8"))
    except (ConfigError, OSError, ValueError) as e:
        print(f"fix_run: FAILED: {e}", file=sys.stderr)
        return EXIT_ERROR
    code = run(task, cfg, load_sdk())
    print(f"fix_run: outcome {json.loads((Path(cfg.out_dir) / 'result.json').read_text())['outcome']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
