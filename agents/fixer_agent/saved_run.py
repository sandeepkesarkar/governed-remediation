"""Check a saved run before it is published (M2-7 publish-only mode).

A saved sandbox tar is only data. Before a script publishes one without running the model again, this module checks,
from the run's own recorded results and not from the tar's presence, that the run really was clean:

  - result.json says the run's outcome was "ready" (written by the fix run itself)
  - sanity.json says the sanity check passed
  - metrics.json is final and holds a real, non-zero cost
  - the cost log has an entry for this same run (same issue, same cost and token counts) whose
    isolation_after is "passed"
  - the tar is there and not empty, and the task is for this issue
  - no pull request was opened from this run already (no pr.json)

It checks only. It runs no model and no isolation check. The full publish checks (publish.py) still run afterwards.

Command line (used by scripts/fix.sh --publish-only):
    python -m agents.fixer_agent.saved_run --fix-dir out/fix --log out/cost-log.jsonl --issue 3
"""
import argparse
import json
import sys
from pathlib import Path


class SavedRunError(Exception):
    """The saved run cannot be published. The message says why."""


def _read(path, what):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SavedRunError(f"cannot read {what} ({Path(path).name})") from None
    if not isinstance(data, dict):
        raise SavedRunError(f"{what} ({Path(path).name}) is not what was expected")
    return data


def _log_entries(path):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        raise SavedRunError("cannot read the cost log") from None
    out = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def verify(fix_dir, log_path, issue):
    """Returns a short summary dict, or raises SavedRunError."""
    fix = Path(fix_dir)
    result = _read(fix / "result.json", "the run result")
    if result.get("outcome") != "ready":
        raise SavedRunError(f"the run's outcome is not ready (it is {result.get('outcome')!r})")
    sanity = _read(fix / "sanity.json", "the sanity result")
    if sanity.get("ok") is not True:
        raise SavedRunError("the sanity check did not pass")
    metrics = _read(fix / "metrics.json", "the metrics")
    cost = metrics.get("cost_usd")
    if metrics.get("final") is not True:
        raise SavedRunError("the metrics are not final")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost <= 0:
        raise SavedRunError("the metrics hold no real cost figure")
    task = _read(fix / "task.json", "the task")
    if task.get("issue") != issue:
        raise SavedRunError(f"the saved run is for a different issue ({task.get('issue')}, not {issue})")
    tar = fix / "tree.tar"
    if not tar.is_file() or tar.stat().st_size == 0:
        raise SavedRunError("there is no saved tar to publish")
    if (fix / "pr.json").exists():
        raise SavedRunError("this run already has a pull request (pr.json exists)")

    matches = [e for e in _log_entries(log_path)
               if e.get("issue") == issue and e.get("final") is True
               and e.get("cost_usd") == cost
               and e.get("input_tokens") == metrics.get("input_tokens")
               and e.get("output_tokens") == metrics.get("output_tokens")]
    if not matches:
        raise SavedRunError("no entry in the cost log belongs to this run")
    entry = matches[-1]
    if entry.get("isolation_after") != "passed":
        raise SavedRunError(f"the isolation check after the run did not pass ({entry.get('isolation_after')})")
    return {"issue": issue, "cost_usd": cost, "isolation_after": entry["isolation_after"],
            "tar_bytes": tar.stat().st_size}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check that a saved run was clean before it is published.")
    ap.add_argument("--fix-dir", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--issue", required=True, type=int)
    args = ap.parse_args(argv)
    try:
        info = verify(args.fix_dir, args.log, args.issue)
    except SavedRunError as e:
        print(f"saved-run: FAILED: {e}", file=sys.stderr)
        return 1
    print(f"saved run verified: issue #{info['issue']}, outcome ready, sanity passed, cost ${info['cost_usd']:.4f}, "
          f"isolation after the run: {info['isolation_after']}, tar {info['tar_bytes']} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
