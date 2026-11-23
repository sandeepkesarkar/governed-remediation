"""Tests for the SARIF reader. Written first. They use small hand-made SARIF, not scan output.

The rule message text below is a marker string. The tests check that it never comes out.
"""
import json

import pytest

from agents.ticket_agent import sarif
from agents.ticket_agent.sarif import Finding, SarifError

SECRET_TEXT = "RULE-MESSAGE-TEXT-MUST-NOT-LEAK"


def rule(rule_id, tags=("CWE-89: Improper Neutralization", "HIGH CONFIDENCE"), level="error"):
    r = {"id": rule_id, "properties": {"tags": list(tags)}}
    if level is not None:
        r["defaultConfiguration"] = {"level": level}
    return r


def result(rule_id, uri="routes/login.ts", line=34, level=None):
    r = {
        "ruleId": rule_id,
        "message": {"text": SECRET_TEXT},
        "locations": [{"physicalLocation": {
            "artifactLocation": {"uri": uri, "uriBaseId": "%SRCROOT%"},
            "region": {"startLine": line, "snippet": {"text": SECRET_TEXT}},
        }}],
    }
    if level:
        r["level"] = level
    return r


def doc(rules, results):
    return {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "Semgrep", "rules": rules}},
                                          "results": results}]}


def test_two_rules_on_one_line_make_one_finding():
    d = doc([rule("a.b.rule-two"), rule("a.b.rule-one")],
            [result("a.b.rule-two"), result("a.b.rule-one")])
    assert sarif.read_findings(d) == [
        Finding("routes/login.ts", 34, "CWE-89", "error", ("a.b.rule-one", "a.b.rule-two"))]


def test_different_lines_are_different_findings():
    d = doc([rule("r1")], [result("r1", line=34), result("r1", line=40)])
    assert [f.line for f in sarif.read_findings(d)] == [34, 40]


def test_same_line_different_cwe_are_different_findings():
    d = doc([rule("r1"), rule("r2", tags=("CWE-79: XSS",))], [result("r1"), result("r2")])
    assert sorted(f.cwe for f in sarif.read_findings(d)) == ["CWE-79", "CWE-89"]


def test_same_rule_twice_on_one_line_is_listed_once():
    d = doc([rule("r1")], [result("r1"), result("r1")])
    assert sarif.read_findings(d)[0].rule_ids == ("r1",)


def test_cwe_comes_from_rule_tags_and_first_cwe_wins():
    d = doc([rule("r1", tags=("OWASP-A03:2021", "CWE-95: Eval", "CWE-89: SQL"))], [result("r1")])
    assert sarif.read_findings(d)[0].cwe == "CWE-95"


def test_result_with_no_cwe_is_rejected_with_a_clear_error():
    d = doc([rule("r1", tags=("OWASP-A03:2021",))], [result("r1", uri="x/y.ts", line=7)])
    with pytest.raises(SarifError) as e:
        sarif.read_findings(d)
    msg = str(e.value)
    assert "no CWE" in msg and "r1" in msg and "x/y.ts:7" in msg
    assert SECRET_TEXT not in msg


def test_rule_with_no_tags_at_all_is_rejected():
    d = doc([{"id": "r1"}], [result("r1")])
    with pytest.raises(SarifError, match="no CWE"):
        sarif.read_findings(d)


def test_result_for_an_unknown_rule_is_rejected():
    d = doc([rule("r1")], [result("other")])
    with pytest.raises(SarifError, match="other"):
        sarif.read_findings(d)


def test_severity_comes_from_the_rule_level_and_highest_wins():
    d = doc([rule("lo", level="warning"), rule("hi", level="error")],
            [result("lo"), result("hi")])
    assert sarif.read_findings(d)[0].severity == "error"


def test_result_level_overrides_the_rule_level():
    d = doc([rule("r1", level="error")], [result("r1", level="note")])
    assert sarif.read_findings(d)[0].severity == "note"


def test_severity_defaults_to_warning_when_nothing_is_set():
    d = doc([rule("r1", level=None)], [result("r1")])
    assert sarif.read_findings(d)[0].severity == "warning"


def test_unknown_severity_is_rejected():
    d = doc([rule("r1", level="loud")], [result("r1")])
    with pytest.raises(SarifError, match="severity"):
        sarif.read_findings(d)


def test_leading_dot_slash_is_removed_from_paths():
    d = doc([rule("r1")], [result("r1", uri="./routes/login.ts")])
    assert sarif.read_findings(d)[0].file == "routes/login.ts"


@pytest.mark.parametrize("uri", ["/src/routes/login.ts", "file:///src/x.ts", "../x.ts", "a/../../x.ts"])
def test_paths_not_relative_to_the_app_root_are_rejected(uri):
    d = doc([rule("r1")], [result("r1", uri=uri)])
    with pytest.raises(SarifError, match="relative to the app root"):
        sarif.read_findings(d)


@pytest.mark.parametrize("uri", ["app/routes/login.ts", "app/app/x.ts"])
def test_a_path_may_start_with_an_app_folder(uri):
    # A real repo can have an app/ folder. Only absolute paths, URLs and .. paths are rejected.
    d = doc([rule("r1")], [result("r1", uri=uri)])
    assert sarif.read_findings(d)[0].file == uri


def test_result_without_location_is_rejected():
    r = result("r1")
    r["locations"] = []
    with pytest.raises(SarifError, match="location"):
        sarif.read_findings(doc([rule("r1")], [r]))


def test_result_without_line_is_rejected():
    r = result("r1")
    del r["locations"][0]["physicalLocation"]["region"]["startLine"]
    with pytest.raises(SarifError, match="line"):
        sarif.read_findings(doc([rule("r1")], [r]))


def test_result_without_rule_id_is_rejected():
    r = result("r1")
    del r["ruleId"]
    with pytest.raises(SarifError, match="ruleId"):
        sarif.read_findings(doc([rule("r1")], [r]))


@pytest.mark.parametrize("bad", [[], "text", {"version": "2.1.0"}, {"runs": []}, {"runs": ["x"]}, {"runs": [{}]}])
def test_wrong_shape_is_rejected(bad):
    with pytest.raises(SarifError):
        sarif.read_findings(bad)


def test_no_field_of_a_finding_holds_message_text():
    d = doc([rule("r1")], [result("r1")])
    f = sarif.read_findings(d)[0]
    assert SECRET_TEXT not in repr(f)


def test_findings_are_sorted_by_file_and_line():
    d = doc([rule("r1")], [result("r1", uri="b.ts", line=1), result("r1", uri="a.ts", line=9),
                           result("r1", uri="a.ts", line=2)])
    assert [(f.file, f.line) for f in sarif.read_findings(d)] == [("a.ts", 2), ("a.ts", 9), ("b.ts", 1)]


def test_no_results_gives_an_empty_list():
    assert sarif.read_findings(doc([rule("r1")], [])) == []


# --- reading a file -------------------------------------------------------------------------

def test_read_file_missing(tmp_path):
    with pytest.raises(SarifError, match="no SARIF file"):
        sarif.read_file(tmp_path / "nope.sarif")


def test_read_file_empty(tmp_path):
    p = tmp_path / "e.sarif"
    p.write_text("")
    with pytest.raises(SarifError, match="empty"):
        sarif.read_file(p)


def test_read_file_not_json(tmp_path):
    p = tmp_path / "b.sarif"
    p.write_text("{not json")
    with pytest.raises(SarifError, match="not valid JSON"):
        sarif.read_file(p)


def test_read_file_ok(tmp_path):
    p = tmp_path / "ok.sarif"
    p.write_text(json.dumps(doc([rule("r1")], [result("r1")])))
    assert len(sarif.read_file(p)) == 1


# --- the expected finding -------------------------------------------------------------------

def test_find_expected_returns_the_match():
    d = doc([rule("r1")], [result("r1")])
    found = sarif.find_expected(sarif.read_findings(d), "routes/login.ts", "CWE-89")
    assert found is not None and found.line == 34


def test_find_expected_returns_none_when_missing():
    d = doc([rule("r1")], [result("r1", uri="routes/search.ts")])
    assert sarif.find_expected(sarif.read_findings(d), "routes/login.ts", "CWE-89") is None


# --- the command line -----------------------------------------------------------------------

def write(tmp_path, d):
    p = tmp_path / "s.sarif"
    p.write_text(json.dumps(d))
    return str(p)


def test_cli_ok_prints_counts_and_rule_ids_only(tmp_path, capsys):
    d = doc([rule("r.one"), rule("r.two")], [result("r.one"), result("r.two"), result("r.one", uri="x.ts", line=1)])
    rc = sarif.main([write(tmp_path, d), "--expect-file", "routes/login.ts", "--expect-cwe", "CWE-89"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "3 results at 2 locations" in out
    assert "routes/login.ts:34 CWE-89" in out and "r.one" in out and "r.two" in out
    assert SECRET_TEXT not in out


def test_cli_missing_expected_finding_fails(tmp_path, capsys):
    d = doc([rule("r1")], [result("r1", uri="routes/search.ts")])
    rc = sarif.main([write(tmp_path, d), "--expect-file", "routes/login.ts", "--expect-cwe", "CWE-89"])
    assert rc == 1
    assert "expected finding" in capsys.readouterr().err


def test_cli_zero_results_fails(tmp_path, capsys):
    rc = sarif.main([write(tmp_path, doc([rule("r1")], []))])
    assert rc == 1
    assert "no results" in capsys.readouterr().err


def test_cli_bad_file_fails(tmp_path, capsys):
    rc = sarif.main([str(tmp_path / "nope.sarif")])
    assert rc == 1
    assert "no SARIF file" in capsys.readouterr().err


def test_cli_without_expectation_only_summarises(tmp_path, capsys):
    rc = sarif.main([write(tmp_path, doc([rule("r1")], [result("r1")]))])
    assert rc == 0
    assert "1 results at 1 locations" in capsys.readouterr().out


def test_result_with_no_rule_id_and_no_location_names_an_unknown_location():
    with pytest.raises(SarifError, match="unknown location"):
        sarif.read_findings(doc([rule("r1")], [{"message": {"text": SECRET_TEXT}}]))


def test_empty_file_path_is_rejected():
    d = doc([rule("r1")], [result("r1", uri="")])
    with pytest.raises(SarifError, match="no file path"):
        sarif.read_findings(d)
