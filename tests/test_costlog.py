"""Tests for the cost log (M2-7). No network, no model, no SDK."""
import json
from datetime import datetime, timezone

import pytest

from agents.fixer_agent import costlog

NOW = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)

METRICS = {"model": "anthropic/claude-sonnet-5-5", "cost_usd": 0.0304, "input_tokens": 20026,
           "output_tokens": 385, "cache_read_tokens": 9750, "cache_write_tokens": 10039,
           "budget_cap_hit": False, "iteration_cap_hit": False, "seconds": 4.3, "final": True}


def write_metrics(tmp_path, **changes):
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps({**METRICS, **changes}))
    return path


def test_build_entry_has_the_agreed_fields_and_nothing_else():
    e = costlog.build_entry(issue=3, metrics=METRICS, outcome="pr_opened", now=NOW)
    assert e == {"timestamp": "2026-11-24T12:00:00Z", "issue": 3, "model": "anthropic/claude-sonnet-5-5",
                 "input_tokens": 20026, "output_tokens": 385, "cache_read_tokens": 9750,
                 "cache_write_tokens": 10039, "cost_usd": 0.0304, "budget_cap_hit": False,
                 "iteration_cap_hit": False, "outcome": "pr_opened", "seconds": 4.3, "final": True}


def test_build_entry_without_metrics_has_unknown_cost():
    e = costlog.build_entry(issue=3, metrics=None, outcome="timeout", now=NOW, model="m")
    assert e["cost_usd"] is None and e["model"] == "m" and e["final"] is False
    assert e["budget_cap_hit"] is None and e["iteration_cap_hit"] is None


def test_append_adds_one_line_and_never_rewrites(tmp_path):
    log = tmp_path / "out" / "cost-log.jsonl"
    costlog.append(log, {"cost_usd": 1.0})
    costlog.append(log, {"cost_usd": 2.0})
    lines = log.read_text().splitlines()
    assert [json.loads(l)["cost_usd"] for l in lines] == [1.0, 2.0]


def test_running_total_sums_costs_and_counts_runs(tmp_path):
    log = tmp_path / "log.jsonl"
    for c in (0.5, 0.25, None):
        costlog.append(log, {"cost_usd": c})
    total, runs, unknown = costlog.running_total(log)
    assert (total, runs, unknown) == (0.75, 3, 1)


def test_running_total_of_a_missing_log_is_zero(tmp_path):
    assert costlog.running_total(tmp_path / "none.jsonl") == (0.0, 0, 0)


def test_running_total_counts_a_damaged_line_as_unknown_not_as_free(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text('{"cost_usd": 1.0}\nnot json\n\n{"cost_usd": "x"}\n')
    assert costlog.running_total(log) == (1.0, 3, 2)


def test_report_prints_this_run_and_the_running_total():
    e = costlog.build_entry(issue=3, metrics=METRICS, outcome="pr_opened", now=NOW)
    text = costlog.report(e, total=0.1234, runs=3, unknown=0)
    assert "$0.0304" in text and "$0.1234" in text and "3 runs" in text
    assert "20026" in text and "385" in text and "pr_opened" in text


def test_report_warns_about_unknown_costs():
    e = costlog.build_entry(issue=3, metrics=None, outcome="timeout", now=NOW, model="m")
    text = costlog.report(e, total=0.0, runs=1, unknown=1)
    assert "unknown" in text.lower()


def test_report_names_a_cap_that_was_hit():
    e = costlog.build_entry(issue=3, metrics={**METRICS, "budget_cap_hit": True}, outcome="budget_cap_hit", now=NOW)
    assert "budget cap was hit" in costlog.report(e, 1.0, 1, 0)
    e = costlog.build_entry(issue=3, metrics={**METRICS, "iteration_cap_hit": True}, outcome="iteration_cap_hit", now=NOW)
    assert "iteration cap was hit" in costlog.report(e, 1.0, 1, 0)


def run(tmp_path, *extra, metrics=True):
    log = tmp_path / "cost-log.jsonl"
    args = ["record", "--log", str(log), "--issue", "3", "--outcome", "pr_opened",
            "--metrics", str(tmp_path / "metrics.json"), *extra]
    return costlog.main(args, now=NOW), log


def test_record_appends_prints_and_succeeds(tmp_path, capsys):
    write_metrics(tmp_path)
    code, log = run(tmp_path)
    out = capsys.readouterr().out
    assert code == 0 and len(log.read_text().splitlines()) == 1
    assert "this run" in out and "running total" in out


def test_a_second_record_adds_to_the_running_total(tmp_path, capsys):
    write_metrics(tmp_path)
    run(tmp_path)
    capsys.readouterr()
    run(tmp_path)
    assert "$0.0608" in capsys.readouterr().out


def test_a_cost_of_exactly_zero_fails_loudly_but_is_still_logged(tmp_path, capsys):
    write_metrics(tmp_path, cost_usd=0.0)
    code, log = run(tmp_path)
    err = capsys.readouterr().err
    assert code == 3 and "ZERO" in err
    assert len(log.read_text().splitlines()) == 1


def test_a_missing_metrics_file_after_a_model_call_fails_loudly(tmp_path, capsys):
    code, log = run(tmp_path)
    assert code == 3 and "no cost figure" in capsys.readouterr().err
    assert json.loads(log.read_text())["cost_usd"] is None


def test_a_run_that_never_called_the_model_may_have_no_metrics(tmp_path, capsys):
    code, log = run(tmp_path, "--no-model-call")
    assert code == 0
    entry = json.loads(log.read_text())
    assert entry["cost_usd"] == 0.0 and entry["final"] is True


def test_a_snapshot_that_is_not_final_is_flagged_as_a_lower_bound(tmp_path, capsys):
    write_metrics(tmp_path, final=False)
    code, _ = run(tmp_path)
    assert code == 0 and "lower bound" in capsys.readouterr().err


def test_a_metrics_file_that_is_not_json_counts_as_missing(tmp_path, capsys):
    (tmp_path / "metrics.json").write_text("{nope")
    code, _ = run(tmp_path)
    assert code == 3


def test_a_negative_or_text_cost_is_rejected_as_missing(tmp_path):
    write_metrics(tmp_path, cost_usd=-1)
    assert run(tmp_path)[0] == 3


def test_record_needs_an_outcome():
    with pytest.raises(SystemExit):
        costlog.main(["record", "--log", "x", "--issue", "3"])
