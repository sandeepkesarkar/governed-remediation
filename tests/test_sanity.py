"""Tests for the sanity-check runner (M2-7). The command runner is faked: nothing runs."""
import pytest

from agents.fixer_agent import sanity

PASS = "\n  3 passing (9ms)\n"


class Exec:
    """Answers each command from a queue of (exit_code, output)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, command, timeout):
        self.calls.append((command, timeout))
        return self.answers.pop(0)


def good():
    return Exec((0, ""), (0, PASS), (0, "  37 passing (12ms)\n"))


def test_parse_mocha_reads_passing_and_failing():
    assert sanity.parse_mocha("  12 passing (3ms)\n  2 failing\n") == (12, 2)
    assert sanity.parse_mocha("nothing useful") == (0, 0)
    assert sanity.parse_mocha("1 passing\n4 passing") == (5, 0)


def test_all_checks_passing_is_ok_and_runs_three_commands():
    ex = good()
    r = sanity.run_sanity(ex)
    assert r.ok and r.reasons == [] and r.passing == 40 and r.failing == 0
    cmds = [c for c, _ in ex.calls]
    assert cmds[0].startswith("test -f ") and sanity.SPEC in cmds[0]
    assert sanity.SPEC in cmds[1] and "npx mocha" in cmds[1]
    assert all(f in cmds[2] for f in sanity.EXISTING)
    assert all(t > 0 for _, t in ex.calls)


def test_a_missing_regression_spec_fails_without_running_mocha():
    ex = Exec((1, ""))
    r = sanity.run_sanity(ex)
    assert not r.ok and "regression test file is missing" in r.reasons[0]
    assert len(ex.calls) == 1


def test_a_failing_regression_spec_fails():
    ex = Exec((0, ""), (1, "  1 passing\n  1 failing\n"), (0, "5 passing"))
    r = sanity.run_sanity(ex)
    assert not r.ok and any("regression test failed" in x for x in r.reasons)


def test_a_spec_with_no_tests_fails_even_with_exit_zero():
    ex = Exec((0, ""), (0, "  0 passing (1ms)\n"), (0, "5 passing"))
    r = sanity.run_sanity(ex)
    assert not r.ok and any("no passing test" in x for x in r.reasons)


def test_an_existing_spec_that_fails_fails_the_check():
    ex = Exec((0, ""), (0, PASS), (1, "  2 failing\n"))
    r = sanity.run_sanity(ex)
    assert not r.ok and any("existing" in x for x in r.reasons)


def test_a_command_that_cannot_run_is_a_failure_not_a_crash():
    def boom(command, timeout):
        raise TimeoutError("slow")
    r = sanity.run_sanity(boom)
    assert not r.ok and "could not run" in r.reasons[0]


def test_output_is_cut_to_the_last_lines_and_scrubbed():
    long = "\n".join(f"line {i}" for i in range(200)) + "\nsk-ant-SECRET123 in output\n"
    ex = Exec((0, ""), (1, long), (0, "5 passing"))
    r = sanity.run_sanity(ex, scrub=["sk-ant-SECRET123"])
    assert len(r.output_tail.splitlines()) <= sanity.TAIL_LINES
    assert "SECRET123" not in r.output_tail and "***" in r.output_tail


def test_the_result_has_a_json_form():
    d = sanity.run_sanity(good()).as_dict()
    assert d["ok"] is True and d["passing"] == 40 and d["reasons"] == []
