"""Tests for the fix run (M2-7): the part that drives OpenHands. The SDK is replaced by a fake.

No network, no model, no paid call. The key below is a made-up marker.
"""
import json
from types import SimpleNamespace

import pytest

from agents.fixer_agent import fix_run

KEY = "sk-ant-FAKEKEYMARKER1234567890"
TASK = {"issue": 3, "prompt": "Fix the thing.", "file": "app/routes/login.ts", "line": 34, "cwe": "CWE-89"}


class RunError(Exception):
    def __init__(self, code):
        super().__init__(f"run failed {code}")
        self.conversation_error = SimpleNamespace(code=code) if code else None


class FakeStats:
    def __init__(self, cost, tokens):
        self.cost, self.tokens = cost, tokens

    def get_combined_metrics(self):
        return SimpleNamespace(accumulated_cost=self.cost, accumulated_token_usage=self.tokens)


def tokens(p=1000, c=200, r=50, w=60):
    return SimpleNamespace(prompt_tokens=p, completion_tokens=c, cache_read_tokens=r, cache_write_tokens=w)


class FakeSDK:
    """Stands in for the OpenHands SDK. `behaviour` decides what conversation.run() does."""

    def __init__(self, behaviour="finish", cost=0.03, status="finished", exec_answers=None, stats_error=False):
        self.behaviour, self.cost, self.status = behaviour, cost, status
        self.exec_answers = exec_answers if exec_answers is not None else [(0, ""), (0, " 3 passing\n"), (0, " 9 passing\n")]
        self.stats_error = stats_error
        self.made = {}
        self.ConversationRunError = RunError

    def LLM(self, **kw):
        self.made["llm"] = kw
        return SimpleNamespace(**kw)

    def make_agent(self, llm):
        self.made["agent_tools"] = ["terminal", "file_editor", "task_tracker"]
        self.made["sub_agents"] = False
        return SimpleNamespace(llm=llm)

    def RemoteWorkspace(self, host, working_dir):
        sdk = self

        class WS:
            def execute_command(self, command, cwd=None, timeout=30.0):
                code, out = sdk.exec_answers.pop(0)
                return SimpleNamespace(exit_code=code, stdout=out, stderr="", timeout_occurred=False)
        self.made["workspace"] = (host, working_dir)
        return WS()

    def Conversation(self, **kw):
        sdk = self
        self.made["conversation"] = kw

        class Conv:
            state = SimpleNamespace(execution_status=sdk.status)

            @property
            def conversation_stats(self):
                if sdk.stats_error:
                    raise RuntimeError("stats down")
                return FakeStats(sdk.cost, tokens())

            def send_message(self, text):
                sdk.made["message"] = text

            def run(self):
                for cb in kw["callbacks"]:
                    cb(SimpleNamespace(model_dump_json=lambda: json.dumps({"kind": "Fake", "x": KEY})))
                if sdk.behaviour in ("budget", "iterations"):
                    raise RunError({"budget": "MaxBudgetReached", "iterations": "MaxIterationsReached"}[sdk.behaviour])
                if sdk.behaviour == "other_error":
                    raise RunError(None)
                if sdk.behaviour == "crash":
                    raise ValueError("boom " + KEY)

            def close(self):
                sdk.made["closed"] = True
        return Conv()


def cfg(tmp_path, **kw):
    base = dict(host="http://sandbox:8000", api_key=KEY, model="anthropic/claude-sonnet-5-5",
                max_budget=1.0, max_iterations=40, out_dir=str(tmp_path), wall_clock=900)
    base.update(kw)
    return fix_run.Config(**base)


def read(tmp_path, name):
    return json.loads((tmp_path / name).read_text())


def test_a_good_run_writes_final_metrics_and_a_ready_result(tmp_path):
    sdk = FakeSDK()
    code = fix_run.run(TASK, cfg(tmp_path), sdk)
    assert code == fix_run.EXIT_READY
    m = read(tmp_path, "metrics.json")
    assert m["final"] is True and m["cost_usd"] == 0.03 and m["input_tokens"] == 1000
    assert m["output_tokens"] == 200 and m["cache_read_tokens"] == 50 and m["cache_write_tokens"] == 60
    assert m["budget_cap_hit"] is False and m["iteration_cap_hit"] is False
    assert m["model"] == "anthropic/claude-sonnet-5-5"
    assert read(tmp_path, "result.json")["outcome"] == "ready"
    assert read(tmp_path, "sanity.json")["ok"] is True
    assert sdk.made["closed"]


def test_the_caps_models_and_sub_agent_setting_reach_the_sdk(tmp_path):
    sdk = FakeSDK()
    fix_run.run(TASK, cfg(tmp_path), sdk)
    conv = sdk.made["conversation"]
    assert conv["max_budget_per_run"] == 1.0 and conv["max_iteration_per_run"] == 40
    assert sdk.made["llm"]["model"] == "anthropic/claude-sonnet-5-5"
    assert sdk.made["sub_agents"] is False
    assert sdk.made["message"] == "Fix the thing."
    assert sdk.made["workspace"] == ("http://sandbox:8000", "/workspace/app")


def test_the_key_never_reaches_the_files(tmp_path):
    fix_run.run(TASK, cfg(tmp_path), FakeSDK())
    for p in tmp_path.iterdir():
        assert KEY not in p.read_text(), p.name
    assert "***" in (tmp_path / "events.jsonl").read_text()


def test_budget_cap_is_recorded_and_no_sanity_check_runs(tmp_path):
    sdk = FakeSDK("budget", cost=1.02)
    code = fix_run.run(TASK, cfg(tmp_path), sdk)
    assert code == fix_run.EXIT_STOPPED
    m = read(tmp_path, "metrics.json")
    assert m["budget_cap_hit"] is True and m["iteration_cap_hit"] is False and m["final"] is True
    assert read(tmp_path, "result.json")["outcome"] == "budget_cap_hit"
    assert not (tmp_path / "sanity.json").exists()
    assert len(sdk.exec_answers) == 3


def test_iteration_cap_is_recorded(tmp_path):
    code = fix_run.run(TASK, cfg(tmp_path), FakeSDK("iterations"))
    assert code == fix_run.EXIT_STOPPED
    assert read(tmp_path, "metrics.json")["iteration_cap_hit"] is True
    assert read(tmp_path, "result.json")["outcome"] == "iteration_cap_hit"


def test_another_run_error_is_an_agent_error(tmp_path):
    code = fix_run.run(TASK, cfg(tmp_path), FakeSDK("other_error"))
    assert code == fix_run.EXIT_STOPPED
    assert read(tmp_path, "result.json")["outcome"] == "agent_error"


def test_a_run_that_ends_in_a_status_other_than_finished_is_an_agent_error(tmp_path):
    code = fix_run.run(TASK, cfg(tmp_path), FakeSDK(status="stuck"))
    assert code == fix_run.EXIT_STOPPED
    assert read(tmp_path, "result.json")["outcome"] == "agent_error"


def test_a_crash_is_reported_without_the_key_and_cost_is_still_read(tmp_path):
    code = fix_run.run(TASK, cfg(tmp_path), FakeSDK("crash"))
    assert code == fix_run.EXIT_ERROR
    r = read(tmp_path, "result.json")
    assert r["outcome"] == "error" and KEY not in json.dumps(r) and "ValueError" in r["reason"]
    assert read(tmp_path, "metrics.json")["cost_usd"] == 0.03


def test_a_failed_sanity_check_means_not_ready(tmp_path):
    sdk = FakeSDK(exec_answers=[(0, ""), (1, "  1 failing\n"), (0, "4 passing")])
    code = fix_run.run(TASK, cfg(tmp_path), sdk)
    assert code == fix_run.EXIT_SANITY
    assert read(tmp_path, "result.json")["outcome"] == "sanity_failed"
    assert read(tmp_path, "sanity.json")["ok"] is False


def test_when_the_metrics_call_fails_the_cost_is_left_out_not_made_up(tmp_path):
    code = fix_run.run(TASK, cfg(tmp_path), FakeSDK(stats_error=True))
    assert code == fix_run.EXIT_READY
    m = read(tmp_path, "metrics.json")
    assert m["cost_usd"] is None and m["final"] is False


def test_progress_snapshots_are_written_while_the_run_goes(tmp_path):
    seen = []
    sdk = FakeSDK()
    orig = fix_run.write_snapshot

    def spy(*a, **k):
        orig(*a, **k)
        seen.append(json.loads((tmp_path / "metrics.json").read_text()))
    fix_run.write_snapshot = spy
    try:
        fix_run.run(TASK, cfg(tmp_path), sdk)
    finally:
        fix_run.write_snapshot = orig
    assert seen and seen[0]["final"] is False


def test_the_deadline_handler_saves_the_last_figure_and_exits(tmp_path):
    exits = []
    sdk = FakeSDK()
    conv = sdk.Conversation(callbacks=[], max_budget_per_run=1, max_iteration_per_run=1)
    fix_run.on_deadline(conv, cfg(tmp_path), started=0.0, exit_fn=exits.append, clock=lambda: 905.0)
    assert exits == [fix_run.EXIT_TIMEOUT]
    assert read(tmp_path, "result.json")["outcome"] == "timeout"
    m = read(tmp_path, "metrics.json")
    assert m["final"] is False and m["seconds"] == 905.0


def test_config_from_the_environment_uses_the_agreed_defaults():
    c = fix_run.config_from_env({"ANTHROPIC_API_KEY": KEY, "AGENT_HOST": "http://s:8000"}, out_dir="/out")
    assert (c.model, c.max_budget, c.max_iterations, c.wall_clock) == (
        "anthropic/claude-sonnet-5-5", 1.0, 40, 840)


def test_config_may_lower_the_caps_but_never_raise_them():
    env = {"ANTHROPIC_API_KEY": KEY, "AGENT_HOST": "h", "MAX_BUDGET": "0.25", "MAX_ITER": "10"}
    c = fix_run.config_from_env(env, out_dir="/out")
    assert (c.max_budget, c.max_iterations) == (0.25, 10)
    for bad in ({"MAX_BUDGET": "2"}, {"MAX_ITER": "41"}, {"MAX_BUDGET": "0"}, {"MAX_ITER": "x"}, {"MAX_BUDGET": "nan"}):
        with pytest.raises(fix_run.ConfigError):
            fix_run.config_from_env({"ANTHROPIC_API_KEY": KEY, "AGENT_HOST": "h", **bad}, out_dir="/out")


def test_config_needs_the_key_and_the_host_and_refuses_another_model():
    with pytest.raises(fix_run.ConfigError, match="ANTHROPIC_API_KEY"):
        fix_run.config_from_env({"AGENT_HOST": "h"}, out_dir="/out")
    with pytest.raises(fix_run.ConfigError, match="AGENT_HOST"):
        fix_run.config_from_env({"ANTHROPIC_API_KEY": KEY}, out_dir="/out")
    with pytest.raises(fix_run.ConfigError, match="model"):
        fix_run.config_from_env({"ANTHROPIC_API_KEY": KEY, "AGENT_HOST": "h", "MODEL": "anthropic/other"}, out_dir="/out")


def test_main_reads_the_task_file_and_runs(tmp_path, monkeypatch):
    task = tmp_path / "task.json"
    task.write_text(json.dumps(TASK))
    monkeypatch.setattr(fix_run, "load_sdk", lambda: FakeSDK())
    out = tmp_path / "o"
    code = fix_run.main(["--task", str(task), "--out", str(out)],
                        env={"ANTHROPIC_API_KEY": KEY, "AGENT_HOST": "http://s:8000"})
    assert code == fix_run.EXIT_READY and (out / "metrics.json").exists()


def test_main_with_a_bad_config_exits_with_a_message_and_no_key(tmp_path, capsys):
    task = tmp_path / "task.json"
    task.write_text(json.dumps(TASK))
    code = fix_run.main(["--task", str(task), "--out", str(tmp_path)],
                        env={"ANTHROPIC_API_KEY": KEY, "AGENT_HOST": "h", "MAX_BUDGET": "99"})
    err = capsys.readouterr().err
    assert code == fix_run.EXIT_ERROR and "MAX_BUDGET" in err and KEY not in err


def test_main_with_an_unreadable_task_is_an_error(tmp_path, capsys):
    code = fix_run.main(["--task", str(tmp_path / "none.json"), "--out", str(tmp_path)],
                        env={"ANTHROPIC_API_KEY": KEY, "AGENT_HOST": "h"})
    assert code == fix_run.EXIT_ERROR
