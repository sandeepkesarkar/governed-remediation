"""Tests for the verify step's evidence module (M2-8). Nothing runs: files are written to a temp folder and
GitHub is faked. The token below is a made-up marker; tests check it never comes out in a comment."""
import json

import pytest

from agents.common.github import GitHubClient, GitHubError
from agents.verify_agent import evidence as ev

TOKEN = "ghp_FAKETOKENMARKER1234567890"
SHA = "a" * 40

PASS_OUT = "\n  3 passing (9ms)\n"
FAIL_OUT = ("\n  login SQL injection\n    1) should not put the email into the SQL text\n    2) should pass email\n"
            "    ✓ should not put the password into the SQL text\n\n  1 passing (9ms)\n  2 failing\n\n"
            "  1) login SQL injection\n       should not put the email into the SQL text:\n"
            "     AssertionError: expected SELECT to not contain ' OR 1=1--\n")

RAW_OK = (":100644 100644 aaa bbb M\tapp/routes/login.ts\n"
          ":000000 100644 000 ccc A\tapp/test/server/loginSqlInjectionSpec.ts\n")


# ---------- scope ----------

def test_scope_accepts_the_expected_change_and_splits_tests_from_sources():
    s = ev.check_scope(RAW_OK)
    assert s["ok"] and s["problems"] == []
    assert s["sources"] == ["routes/login.ts"]
    assert s["tests"] == ["test/server/loginSqlInjectionSpec.ts"]


@pytest.mark.parametrize("raw, word", [
    ("", "changes nothing"),
    (":100644 100644 a b M\tapp/frontend/x.ts\n", "outside the allowed"),
    (":100644 100644 a b M\tdocs/x.md\n", "outside the allowed"),
    (":100644 000000 a 0 D\tapp/routes/login.ts\n", "deleted"),
    (":100644 100755 a b M\tapp/routes/login.ts\n", "mode"),
    (":000000 120000 0 b A\tapp/routes/link.ts\n", "mode"),
    (":100644 100644 a b R090\tapp/routes/a.ts\n", "deleted or renamed"),
    (":100644 100644 a b M\tapp/routes/a b.ts\n", "unsafe path"),
    (":100644 100644 a b M\tapp/routes/../../x.ts\n", "unsafe path"),
    ("garbage line\n", "cannot read"),
])
def test_scope_refuses_each_bad_change(raw, word):
    s = ev.check_scope(raw)
    assert not s["ok"]
    assert any(word in p for p in s["problems"]), s["problems"]


def test_scope_refuses_too_many_files():
    raw = "".join(f":000000 100644 0 b A\tapp/test/server/s{i}.ts\n" for i in range(ev.MAX_FILES + 1))
    s = ev.check_scope(raw)
    assert not s["ok"] and any("too many" in p for p in s["problems"])


# ---------- mocha ----------

def test_mocha_summary_and_titles():
    assert ev.mocha_summary(PASS_OUT) == (3, 0)
    assert ev.mocha_summary(FAIL_OUT) == (1, 2)
    assert ev.mocha_summary("nothing") is None
    assert ev.failing_titles(FAIL_OUT) == ["should not put the email into the SQL text", "should pass email"]
    assert ev.failing_titles(PASS_OUT) == []


def test_failure_excerpt_starts_at_the_failures_and_is_capped():
    ex = ev.failure_excerpt(FAIL_OUT + "x" * 5000)
    assert ex.startswith("2 failing") or "AssertionError" in ex
    assert len(ex) <= ev.EXCERPT_CHARS + 20
    assert ev.failure_excerpt(PASS_OUT) == ""


# ---------- one folder per run ----------

def put(d, name, text):
    (d / name).write_text(text)


def spec_files(d, after=(0, PASS_OUT), before=(1, FAIL_OUT)):
    for stem, (rc, out) in (("spec-after", after), ("spec-before", before)):
        put(d, f"{stem}.rc", f"{rc}\n")
        put(d, f"{stem}.txt", out)


def test_regression_passes_when_it_fails_before_and_passes_after(tmp_path):
    spec_files(tmp_path)
    r = ev.check_regression(tmp_path)
    assert r["status"] == ev.PASS
    assert "Fails on" in " ".join(r["lines"]) and "Passes on" in " ".join(r["lines"])


def test_regression_fails_when_the_spec_also_passes_on_unfixed_code(tmp_path):
    spec_files(tmp_path, before=(0, PASS_OUT))
    r = ev.check_regression(tmp_path)
    assert r["status"] == ev.FAIL and "does not tell" in r["headline"]


def test_regression_fails_when_the_spec_fails_on_the_fix(tmp_path):
    spec_files(tmp_path, after=(1, FAIL_OUT))
    assert ev.check_regression(tmp_path)["status"] == ev.FAIL


def test_regression_is_an_error_when_the_unfixed_run_crashed_before_any_test(tmp_path):
    spec_files(tmp_path, before=(1, "SyntaxError: boom\n"))
    r = ev.check_regression(tmp_path)
    assert r["status"] == ev.ERROR


def test_regression_not_run_without_results(tmp_path):
    assert ev.check_regression(tmp_path)["status"] == ev.NOT_RUN


def test_regression_error_when_the_fixed_run_has_no_summary(tmp_path):
    spec_files(tmp_path, after=(1, "Cannot find module\n"))
    assert ev.check_regression(tmp_path)["status"] == ev.ERROR


def suite(d, stem, rc, out):
    put(d, f"{stem}.rc", f"{rc}\n")
    put(d, f"{stem}.txt", out)


def test_suite_passes(tmp_path):
    suite(tmp_path, "suite-pr", 0, "\n  120 passing (3s)\n")
    r = ev.check_suite(tmp_path)
    assert r["status"] == ev.PASS and "120" in r["headline"]


def test_suite_fails_on_new_failures(tmp_path):
    suite(tmp_path, "suite-pr", 1, FAIL_OUT)
    suite(tmp_path, "suite-base", 0, "\n  99 passing\n")
    r = ev.check_suite(tmp_path)
    assert r["status"] == ev.FAIL and "should pass email" in "\n".join(r["lines"])


def test_suite_warns_when_every_failure_also_fails_on_main(tmp_path):
    suite(tmp_path, "suite-pr", 1, FAIL_OUT)
    suite(tmp_path, "suite-base", 1, FAIL_OUT)
    r = ev.check_suite(tmp_path)
    assert r["status"] == ev.WARN and "also fail" in r["headline"]


def test_suite_fails_when_failures_are_not_comparable(tmp_path):
    suite(tmp_path, "suite-pr", 1, FAIL_OUT)
    assert ev.check_suite(tmp_path)["status"] == ev.FAIL


def test_suite_error_without_summary_and_not_run_without_files(tmp_path):
    assert ev.check_suite(tmp_path)["status"] == ev.NOT_RUN
    suite(tmp_path, "suite-pr", 1, "crashed\n")
    assert ev.check_suite(tmp_path)["status"] == ev.ERROR


def test_suite_error_when_exit_is_zero_but_nothing_ran(tmp_path):
    suite(tmp_path, "suite-pr", 0, "\n  0 passing\n")
    assert ev.check_suite(tmp_path)["status"] == ev.ERROR


# ---------- scan ----------

def sarif_doc(*results):
    rules = [{"id": "r.sqli", "properties": {"tags": ["CWE-89: SQL Injection"]}},
             {"id": "r.other", "properties": {"tags": ["CWE-79: XSS"]}}]
    res = [{"ruleId": rid, "level": "error", "message": {"text": "TEXT"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri},
                                                "region": {"startLine": line}}}]}
           for rid, uri, line in results]
    return {"runs": [{"tool": {"driver": {"rules": rules}}, "results": res}]}


FINDING = {"issue": 3, "file": "app/routes/login.ts", "line": 34, "cwe": "CWE-89"}


def scan_files(d, doc, rc=0):
    put(d, "scan.rc", f"{rc}\n")
    if doc is not None:
        put(d, "semgrep-pr.sarif", json.dumps(doc))


def test_scan_passes_when_the_finding_is_gone_but_other_results_remain(tmp_path):
    scan_files(tmp_path, sarif_doc(("r.other", "routes/search.ts", 10)))
    r = ev.check_scan(tmp_path, FINDING)
    assert r["status"] == ev.PASS and "1 results" in r["headline"]


def test_scan_fails_when_the_finding_is_still_there(tmp_path):
    scan_files(tmp_path, sarif_doc(("r.sqli", "routes/login.ts", 36)))
    r = ev.check_scan(tmp_path, FINDING)
    assert r["status"] == ev.FAIL and "36" in " ".join(r["lines"])


def test_scan_never_copies_message_text(tmp_path):
    scan_files(tmp_path, sarif_doc(("r.sqli", "routes/login.ts", 36)))
    assert "TEXT" not in json.dumps(ev.check_scan(tmp_path, FINDING))


def test_scan_error_cases(tmp_path):
    assert ev.check_scan(tmp_path, FINDING)["status"] == ev.NOT_RUN
    scan_files(tmp_path, None, rc=1)
    assert ev.check_scan(tmp_path, FINDING)["status"] == ev.ERROR
    scan_files(tmp_path, {"runs": [{"tool": {"driver": {"rules": []}}, "results": []}]})
    r = ev.check_scan(tmp_path, FINDING)
    assert r["status"] == ev.ERROR and "empty" in r["headline"]
    put(tmp_path, "semgrep-pr.sarif", "not json")
    assert ev.check_scan(tmp_path, FINDING)["status"] == ev.ERROR


# ---------- exploit ----------

def exploit_files(d, rc, ok=True, build_rc=0):
    put(d, "build.rc", f"{build_rc}\n")
    if rc is not None:
        put(d, "exploit.rc", f"{rc}\n")
        put(d, "exploit.json", json.dumps({"attack_status": 401, "outcome": "x"}))
    put(d, "login-check.json", json.dumps({"ok": ok, "status": 200 if ok else 401}))


def test_exploit_passes_when_the_attack_fails_and_a_real_login_works(tmp_path):
    exploit_files(tmp_path, 1)
    r = ev.check_exploit(tmp_path)
    assert r["status"] == ev.PASS


def test_exploit_fails_when_the_attack_succeeds(tmp_path):
    exploit_files(tmp_path, 0)
    r = ev.check_exploit(tmp_path)
    assert r["status"] == ev.FAIL and "succeeded" in r["headline"]


def test_exploit_fails_when_the_real_login_is_broken_too(tmp_path):
    exploit_files(tmp_path, 1, ok=False)
    r = ev.check_exploit(tmp_path)
    assert r["status"] == ev.FAIL and "legitimate" in r["headline"]


@pytest.mark.parametrize("rc", [2, 3, 9])
def test_exploit_error_for_control_failure_refusal_or_unknown(tmp_path, rc):
    exploit_files(tmp_path, rc)
    assert ev.check_exploit(tmp_path)["status"] == ev.ERROR


def test_exploit_not_run_when_the_build_failed_or_nothing_ran(tmp_path):
    exploit_files(tmp_path, None, build_rc=1)
    r = ev.check_exploit(tmp_path)
    assert r["status"] == ev.ERROR and "build" in r["headline"]
    assert ev.check_exploit(tmp_path.parent)["status"] == ev.NOT_RUN


def test_exploit_error_when_the_real_login_check_is_missing(tmp_path):
    exploit_files(tmp_path, 1)
    (tmp_path / "login-check.json").unlink()
    assert ev.check_exploit(tmp_path)["status"] == ev.ERROR


# ---------- the comment ----------

PR = {"number": 13, "head_sha": SHA, "base_sha": "b" * 40, "title": "Fix: CWE-89", "issue": 3}


def full_run(d):
    put(d, "scope.json", json.dumps(ev.check_scope(RAW_OK)))
    spec_files(d)
    suite(d, "suite-pr", 0, "\n  120 passing (3s)\n")
    scan_files(d, sarif_doc(("r.other", "routes/search.ts", 10)))
    exploit_files(d, 1)
    put(d, "pr.json", json.dumps(PR))
    put(d, "finding.json", json.dumps(FINDING))
    put(d, "behind.txt", "0\n")


def test_report_all_pass(tmp_path):
    full_run(tmp_path)
    results = ev.evaluate(tmp_path)
    body = ev.render(results, PR, FINDING, now="2026-11-25 10:00 UTC")
    assert body.startswith(ev.MARKER)
    assert "All four checks passed" in body
    for word in ("Regression test", "Test suite", "Re-scan", "Exploit"):
        assert word in body
    assert "no model call" in body.lower() and SHA[:12] in body
    assert ev.overall(results)[0] is True


def test_report_says_plainly_when_something_did_not_verify(tmp_path):
    full_run(tmp_path)
    suite(tmp_path, "suite-pr", 1, FAIL_OUT)
    exploit_files(tmp_path, 0)
    results = ev.evaluate(tmp_path)
    body = ev.render(results, PR, FINDING, now="x")
    ok, text = ev.overall(results)
    assert not ok and "2 of 4" in text
    assert "did not verify cleanly" in body and "FAIL" in body


def test_report_notes_a_scope_problem_and_a_pull_request_behind_main(tmp_path):
    full_run(tmp_path)
    put(tmp_path, "scope.json", json.dumps(ev.check_scope(":100644 100644 a b M\tdocs/x.md\n")))
    put(tmp_path, "behind.txt", "4\n")
    body = ev.render(ev.evaluate(tmp_path), PR, FINDING, now="x")
    assert "outside the allowed" in body and "4 commits behind" in body


def test_report_survives_an_empty_folder(tmp_path):
    results = ev.evaluate(tmp_path)
    body = ev.render(results, PR, FINDING, now="x")
    assert "NOT RUN" in body and ev.overall(results)[0] is False


def test_report_is_capped_and_scrubs_the_token(tmp_path):
    full_run(tmp_path)
    put(tmp_path, "spec-before.txt", FAIL_OUT + TOKEN + "y" * 100000)
    body = ev.render(ev.evaluate(tmp_path), PR, FINDING, now="x", secret=TOKEN)
    assert TOKEN not in body and len(body) <= ev.MAX_COMMENT_CHARS


# ---------- GitHub: one comment, updated on a second run ----------

class Transport:
    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, json.loads(body) if body else None))
        return self.answers.pop(0)


def client(*answers):
    t = Transport(*answers)
    return GitHubClient(TOKEN, "o/r", transport=t), t


def test_post_creates_the_comment_when_none_has_the_marker():
    c, t = client((200, [{"id": 1, "body": "hello"}]), (201, {"id": 2, "html_url": "u2"}))
    assert ev.post_comment(c, 13, ev.MARKER + "\nbody") == ("created", 2, "u2")
    assert t.calls[1][0] == "POST" and t.calls[1][1].endswith("/issues/13/comments")


def test_post_updates_its_own_comment_instead_of_adding_another():
    c, t = client((200, [{"id": 7, "body": ev.MARKER + "\nold"}]), (200, {"id": 7, "html_url": "u7"}))
    assert ev.post_comment(c, 13, ev.MARKER + "\nnew") == ("updated", 7, "u7")
    assert t.calls[1][0] == "PATCH" and t.calls[1][1].endswith("/issues/comments/7")


def test_client_pull_request_and_comment_calls():
    c, t = client((200, {"number": 13}), (200, [{"id": i} for i in range(100)]), (200, []))
    assert c.get_pull_request(13) == {"number": 13}
    assert t.calls[0][1].endswith("/pulls/13")
    assert len(c.list_issue_comments(13)) == 100
    assert "page=1" in t.calls[1][1] and "page=2" in t.calls[2][1]


def test_client_comment_errors_name_no_token():
    c, _ = client((403, {"message": "no"}))
    with pytest.raises(GitHubError) as e:
        c.create_issue_comment(13, "x")
    assert TOKEN not in str(e.value)


# ---------- pr-info ----------

def pr_json(**over):
    pr = {"number": 13, "state": "open", "title": "Fix", "body": "Closes #3\n\ntext",
          "head": {"sha": SHA, "repo": {"full_name": "o/r"}}, "base": {"ref": "main"}}
    pr.update(over)
    return pr


def test_pr_info_reads_the_head_and_the_closed_issue():
    c, _ = client((200, pr_json()))
    info = ev.pr_info(c, 13, "o/r")
    assert info["head_sha"] == SHA and info["issue"] == 3 and info["number"] == 13


@pytest.mark.parametrize("over, word", [
    ({"state": "closed"}, "not open"),
    ({"head": {"sha": SHA, "repo": {"full_name": "x/fork"}}}, "another repository"),
    ({"head": {"sha": SHA, "repo": None}}, "another repository"),
    ({"head": {"sha": "zz", "repo": {"full_name": "o/r"}}}, "commit"),
    ({"base": {"ref": "dev"}}, "main"),
    ({"body": "no link"}, "which issue it closes"),
    ({"body": None}, "which issue it closes"),
])
def test_pr_info_refuses_each_bad_pull_request(over, word):
    c, _ = client((200, pr_json(**over)))
    with pytest.raises(ev.VerifyError) as e:
        ev.pr_info(c, 13, "o/r")
    assert word in str(e.value)


def test_finding_from_issue_reads_the_fingerprint_marker():
    body = "text\n<!-- gr:fingerprint app/routes/login.ts:34:CWE-89 -->\n"
    c, _ = client((200, {"number": 3, "body": body}))
    assert ev.finding_from_issue(c, 3) == {"issue": 3, "file": "app/routes/login.ts", "line": 34, "cwe": "CWE-89"}
    c, _ = client((200, {"number": 3, "body": "nothing"}))
    with pytest.raises(ev.VerifyError):
        ev.finding_from_issue(c, 3)


# ---------- command line ----------

def test_cli_pr_info_scope_and_report_round_trip(tmp_path, monkeypatch):
    t = Transport((200, pr_json()), (200, {"number": 3, "body": "<!-- gr:fingerprint app/routes/login.ts:34:CWE-89 -->"}))
    env = {"GITHUB_VERIFY_TOKEN": TOKEN}
    assert ev.main(["pr-info", "--repo", "o/r", "--pr", "13", "--dir", str(tmp_path)], env=env, transport=t) == 0
    assert json.loads((tmp_path / "pr.json").read_text())["head_sha"] == SHA
    assert json.loads((tmp_path / "finding.json").read_text())["cwe"] == "CWE-89"

    (tmp_path / "diff.raw").write_text(RAW_OK)
    assert ev.main(["scope", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "changed-tests.txt").read_text().split() == ["test/server/loginSqlInjectionSpec.ts"]
    assert (tmp_path / "changed-sources.txt").read_text().split() == ["routes/login.ts"]

    (tmp_path / "diff.raw").write_text(":100644 100644 a b M\tdocs/x.md\n")
    assert ev.main(["scope", "--dir", str(tmp_path)]) == 1
    assert (tmp_path / "changed-sources.txt").read_text() == ""

    full_run(tmp_path)
    t2 = Transport((200, []), (201, {"id": 5, "html_url": "https://github.com/o/r/pull/13#issuecomment-5"}),
                   (200, []), (201, {"id": 6, "html_url": "x"}))
    code = ev.main(["report", "--dir", str(tmp_path), "--repo", "o/r", "--pr", "13", "--post"],
                   env=env, transport=t2)
    assert code == 0
    assert (tmp_path / "comment.md").read_text().startswith(ev.MARKER)
    assert t2.calls[1][2]["body"].startswith(ev.MARKER)
    summary = t2.calls[3][2]["body"]
    assert t2.calls[3][1].endswith("/issues/3/comments") and summary.startswith(ev.SUMMARY_MARKER)
    assert "https://github.com/o/r/pull/13#issuecomment-5" in summary and "https://github.com/o/r/pull/13" in summary
    assert (tmp_path / "summary.md").read_text() == summary


def test_cli_report_exit_codes(tmp_path, capsys):
    full_run(tmp_path)
    assert ev.main(["report", "--dir", str(tmp_path), "--repo", "o/r", "--pr", "13"]) == 0
    suite(tmp_path, "suite-pr", 1, FAIL_OUT)
    assert ev.main(["report", "--dir", str(tmp_path), "--repo", "o/r", "--pr", "13"]) == 1
    env = {"GITHUB_VERIFY_TOKEN": TOKEN}
    t = Transport((200, []), (403, {"message": "no"}))
    assert ev.main(["report", "--dir", str(tmp_path), "--repo", "o/r", "--pr", "13", "--post"],
                   env=env, transport=t) == 3
    err = capsys.readouterr().err
    assert TOKEN not in err and "comment.md" in err
    assert ev.main(["report", "--dir", str(tmp_path), "--repo", "o/r", "--pr", "13", "--post"], env={}) == 3


def test_cli_pr_info_failures(tmp_path, capsys):
    assert ev.main(["pr-info", "--repo", "o/r", "--pr", "13", "--dir", str(tmp_path)], env={}) == 1
    t = Transport((200, pr_json(state="closed")))
    assert ev.main(["pr-info", "--repo", "o/r", "--pr", "13", "--dir", str(tmp_path)],
                   env={"GITHUB_VERIFY_TOKEN": TOKEN}, transport=t) == 1
    assert "not open" in capsys.readouterr().err
    assert ev.main(["scope", "--dir", str(tmp_path / "missing")]) == 1


# ---------- why something did not run ----------

def test_nothing_runs_when_the_scope_check_failed_and_the_comment_says_why(tmp_path):
    put(tmp_path, "scope.json", json.dumps(ev.check_scope(":100644 100644 a b M\tdocs/x.md\n")))
    for fn in (ev.check_regression, ev.check_suite, ev.check_exploit):
        r = fn(tmp_path)
        assert r["status"] == ev.NOT_RUN and "outside what" in r["headline"]
    assert ev.check_scan(tmp_path, FINDING)["status"] == ev.NOT_RUN


def test_a_failed_dependency_install_is_an_error_not_a_silent_skip(tmp_path):
    put(tmp_path, "tests-install.rc", "1\n")
    put(tmp_path, "tests-install.log", "npm ERR! network\n")
    for fn in (ev.check_regression, ev.check_suite):
        r = fn(tmp_path)
        assert r["status"] == ev.ERROR and "install" in r["headline"]
        assert "npm ERR" in r["output"][0][1]


def test_exploit_error_shows_the_app_log_when_the_container_did_not_start(tmp_path):
    put(tmp_path, "build.rc", "0\n")
    put(tmp_path, "login-check.json", json.dumps({"ok": False, "status": None}))
    put(tmp_path, "app.log", "Error: boom\n")
    r = ev.check_exploit(tmp_path)
    assert r["status"] == ev.ERROR and "boom" in r["output"][0][1]


def test_summary_is_short_links_both_and_has_its_own_marker(tmp_path):
    full_run(tmp_path)
    results = ev.evaluate(tmp_path)
    text = ev.render_summary(results, PR, FINDING, "o/r", "https://github.com/o/r/pull/13#issuecomment-5")
    assert text.startswith(ev.SUMMARY_MARKER) and ev.MARKER not in text
    assert "All four checks passed" in text and "#13" in text and len(text) < 1500
    results["suite"] = {"status": ev.FAIL, "headline": "h", "lines": [], "output": []}
    assert "did not verify cleanly" in ev.render_summary(results, PR, FINDING, "o/r", "u")


def test_issue_summary_failure_is_reported_after_the_pr_comment_was_posted(tmp_path, capsys):
    full_run(tmp_path)
    t = Transport((200, []), (201, {"id": 5, "html_url": "u"}), (200, []), (403, {"message": "no"}))
    code = ev.main(["report", "--dir", str(tmp_path), "--repo", "o/r", "--pr", "13", "--post"],
                   env={"GITHUB_VERIFY_TOKEN": TOKEN}, transport=t)
    err = capsys.readouterr().err
    assert code == 3 and "issue #3" in err and "summary.md" in err and TOKEN not in err
