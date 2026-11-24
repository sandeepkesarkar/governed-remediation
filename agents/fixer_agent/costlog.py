"""The cost log for the fix step (M2-7). One line per run, append only, kept in out/ (git ignores it).

Each line is one JSON object: timestamp, issue, model, token counts, cost in dollars, whether the
budget or iteration cap was hit, and the outcome. After each run this module prints that run's cost and
the running total summed from the whole log. There is no database.

A reported cost of exactly zero is treated as a failure of the metrics call, not as a free run.

Command line (used by scripts/fix.sh):
    python -m agents.fixer_agent.costlog record --log out/cost-log.jsonl --issue 3 \\
        --metrics out/fix/metrics.json --outcome pr_opened [--no-model-call]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MODEL = "anthropic/claude-sonnet-5-5"
EXIT_COST_PROBLEM = 3


def build_entry(*, issue, metrics, outcome, now=None, model=DEFAULT_MODEL, no_model_call=False):
    """One log line. With no metrics, the cost is unknown (None), unless no model call was made (then 0.0)."""
    now = now or datetime.now(timezone.utc)
    m = metrics or {}
    cost = m.get("cost_usd")
    if metrics is None and no_model_call:
        cost = 0.0
    return {
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issue": issue,
        "model": m.get("model", model),
        "input_tokens": m.get("input_tokens"),
        "output_tokens": m.get("output_tokens"),
        "cache_read_tokens": m.get("cache_read_tokens"),
        "cache_write_tokens": m.get("cache_write_tokens"),
        "cost_usd": cost,
        "budget_cap_hit": m.get("budget_cap_hit"),
        "iteration_cap_hit": m.get("iteration_cap_hit"),
        "outcome": outcome,
        "seconds": m.get("seconds"),
        "final": bool(m.get("final", True)) if metrics is not None or no_model_call else False,
    }


def append(path, entry):
    """Add one line. Never rewrites what is already there."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def running_total(path):
    """(total dollars, number of runs, number of runs whose cost is unknown). A damaged line is unknown, not free."""
    path = Path(path)
    if not path.exists():
        return 0.0, 0, 0
    total, runs, unknown = 0.0, 0, 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        runs += 1
        try:
            cost = json.loads(line).get("cost_usd")
        except (ValueError, AttributeError):
            cost = None
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
            total += cost
        else:
            unknown += 1
    return round(total, 6), runs, unknown


def report(entry, total, runs, unknown):
    cost = entry["cost_usd"]
    this = f"${cost:.4f}" if isinstance(cost, (int, float)) else "unknown"
    lines = [
        f"cost: this run {this} ({entry['model']}, issue #{entry['issue']}, outcome {entry['outcome']})",
        f"cost: tokens in {entry['input_tokens']}, out {entry['output_tokens']}, "
        f"cache read {entry['cache_read_tokens']}, cache write {entry['cache_write_tokens']}",
        f"cost: running total ${total:.4f} over {runs} runs (from the log)",
    ]
    if entry["budget_cap_hit"]:
        lines.append("cost: the budget cap was hit")
    if entry["iteration_cap_hit"]:
        lines.append("cost: the iteration cap was hit")
    if unknown:
        lines.append(f"cost: WARNING {unknown} run(s) in the log have an unknown cost, so the total is a lower bound")
    return "\n".join(lines)


def _read_metrics(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cost = data.get("cost_usd") if isinstance(data, dict) else None
    if not isinstance(data, dict) or isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
        return None
    return data


def main(argv=None, now=None):
    ap = argparse.ArgumentParser(description="Record one fixer run in the cost log and print the totals.")
    sub = ap.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--log", required=True)
    rec.add_argument("--issue", required=True, type=int)
    rec.add_argument("--outcome", required=True)
    rec.add_argument("--metrics", help="the metrics.json the fix run wrote")
    rec.add_argument("--model", default=DEFAULT_MODEL)
    rec.add_argument("--no-model-call", action="store_true", help="the run stopped before any model call")
    args = ap.parse_args(argv)

    metrics = _read_metrics(args.metrics) if args.metrics else None
    entry = build_entry(issue=args.issue, metrics=metrics, outcome=args.outcome, now=now,
                        model=args.model, no_model_call=args.no_model_call)
    append(args.log, entry)
    total, runs, unknown = running_total(args.log)
    print(report(entry, total, runs, unknown))

    code = 0
    if not args.no_model_call:
        if metrics is None:
            print("cost: FAILED: no cost figure for a run that called the model. Check the Anthropic console "
                  "before running again", file=sys.stderr)
            code = EXIT_COST_PROBLEM
        elif metrics["cost_usd"] == 0:
            print("cost: FAILED: the reported cost is exactly ZERO. The metrics call did not work. "
                  "This run was not free", file=sys.stderr)
            code = EXIT_COST_PROBLEM
        elif not entry["final"]:
            print("cost: WARNING the figure is a lower bound: the run stopped before the final count. "
                  "Check the Anthropic console", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
