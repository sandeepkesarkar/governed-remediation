"""Tests for the check on a saved run (M2-7 publish-only mode). Files are built in the test. No network."""
import json

import pytest

from agents.fixer_agent import saved_run

METRICS = {"model": "anthropic/claude-sonnet-5-5", "cost_usd": 0.1076, "input_tokens": 141819,
           "output_tokens": 4288, "final": True}
ENTRY = {"issue": 3, "cost_usd": 0.1076, "input_tokens": 141819, "output_tokens": 4288, "final": True,
         "outcome": "publish_failed", "run_outcome": "publish_failed", "isolation_after": "passed"}
OLD_ENTRY = {"issue": 3, "cost_usd": 0.1417, "input_tokens": 220146, "output_tokens": 5744, "final": True,
             "outcome": "sanity_failed"}


def build(tmp_path, result=None, sanity=None, metrics=None, entries=None, tar=True, pr=False, task=None):
    fix = tmp_path / "fix"
    fix.mkdir()
    (fix / "result.json").write_text(json.dumps(result or {"outcome": "ready", "reason": ""}))
    (fix / "sanity.json").write_text(json.dumps(sanity or {"ok": True, "passing": 40, "failing": 0}))
    (fix / "metrics.json").write_text(json.dumps(metrics or METRICS))
    (fix / "task.json").write_text(json.dumps(task or {"issue": 3}))
    if tar:
        (fix / "tree.tar").write_bytes(b"x" * 10)
    if pr:
        (fix / "pr.json").write_text("{}")
    log = tmp_path / "cost-log.jsonl"
    log.write_text("".join(json.dumps(e) + "\n" for e in (entries if entries is not None else [OLD_ENTRY, ENTRY])))
    return fix, log


def test_a_good_saved_run_is_accepted(tmp_path):
    fix, log = build(tmp_path)
    info = saved_run.verify(fix, log, 3)
    assert info["cost_usd"] == 0.1076 and info["isolation_after"] == "passed"


@pytest.mark.parametrize("changes,message", [
    ({"result": {"outcome": "sanity_failed", "reason": "x"}}, "outcome is not ready"),
    ({"sanity": {"ok": False, "passing": 1, "failing": 2}}, "sanity check did not pass"),
    ({"metrics": {**METRICS, "final": False}}, "not final"),
    ({"metrics": {**METRICS, "cost_usd": 0.0}}, "cost"),
    ({"metrics": {**METRICS, "cost_usd": None}}, "cost"),
    ({"tar": False}, "saved tar"),
    ({"pr": True}, "already has a pull request"),
    ({"task": {"issue": 4}}, "different issue"),
])
def test_a_saved_run_that_is_not_clean_is_refused(tmp_path, changes, message):
    fix, log = build(tmp_path, **changes)
    with pytest.raises(saved_run.SavedRunError, match=message):
        saved_run.verify(fix, log, 3)


def test_isolation_must_have_passed_in_the_logged_entry(tmp_path):
    for i, bad in enumerate(("FAILED: client: x", "not_checked", None)):
        d = tmp_path / f"r{i}"
        d.mkdir()
        entry = {**ENTRY}
        if bad is None:
            del entry["isolation_after"]
        else:
            entry["isolation_after"] = bad
        fix, log = build(d, entries=[entry])
        with pytest.raises(saved_run.SavedRunError, match="isolation"):
            saved_run.verify(fix, log, 3)


def test_the_log_entry_must_belong_to_this_run(tmp_path):
    fix, log = build(tmp_path, entries=[OLD_ENTRY])
    with pytest.raises(saved_run.SavedRunError, match="no entry in the cost log"):
        saved_run.verify(fix, log, 3)
    other = tmp_path / "other"
    other.mkdir()
    fix, log = build(other, entries=[{**ENTRY, "issue": 9}])
    with pytest.raises(saved_run.SavedRunError, match="no entry in the cost log"):
        saved_run.verify(fix, log, 3)


def test_a_missing_or_damaged_log_is_refused(tmp_path):
    fix, log = build(tmp_path)
    log.write_text("not json\n")
    with pytest.raises(saved_run.SavedRunError, match="no entry in the cost log"):
        saved_run.verify(fix, log, 3)
    log.unlink()
    with pytest.raises(saved_run.SavedRunError, match="cannot read the cost log"):
        saved_run.verify(fix, log, 3)


def test_missing_run_files_are_refused(tmp_path):
    fix, log = build(tmp_path)
    (fix / "result.json").unlink()
    with pytest.raises(saved_run.SavedRunError, match="result.json"):
        saved_run.verify(fix, log, 3)


def test_main_prints_and_returns_the_exit_code(tmp_path, capsys):
    fix, log = build(tmp_path)
    assert saved_run.main(["--fix-dir", str(fix), "--log", str(log), "--issue", "3"]) == 0
    assert "saved run verified" in capsys.readouterr().out
    (fix / "tree.tar").unlink()
    assert saved_run.main(["--fix-dir", str(fix), "--log", str(log), "--issue", "3"]) == 1
    assert "FAILED" in capsys.readouterr().err
