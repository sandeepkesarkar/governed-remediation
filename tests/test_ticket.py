"""Tests for the ticket step. Written first. GitHub is faked: no network, no token.

The rule message text in the sample SARIF is a marker string. The tests check that it
never reaches a ticket.
"""
import json

import pytest

from agents.ticket_agent import sarif, ticket
from agents.ticket_agent.github import GitHubError
from agents.ticket_agent.ticket import TicketError
from tests.test_sarif import SECRET_TEXT, doc, result, rule

REPO = "o/r"
SHA = "a" * 40
TOKEN = "ghp_FAKETOKENMARKER1234567890"
LINE_TEXT = "db.query('SELECT * FROM Users WHERE email = ' + email)"


class FakeClient:
    """Keeps issues in memory, like the GitHub API would."""

    def __init__(self, issues=None):
        self.issues = list(issues or [])
        self.created, self.updated, self.labels_ensured = [], [], []

    def list_issues(self, label):
        return list(self.issues)

    def ensure_label(self, name, color):
        self.labels_ensured.append(name)

    def create_issue(self, title, body, labels):
        issue = {"number": 100 + len(self.issues), "title": title, "body": body, "labels": list(labels),
                 "state": "open", "html_url": f"https://github.com/{REPO}/issues/{100 + len(self.issues)}"}
        self.issues.append(issue)
        self.created.append(issue)
        return issue

    def update_issue(self, number, body):
        for i in self.issues:
            if i["number"] == number:
                i["body"] = body
        self.updated.append(number)
        return {"number": number}


def findings(*specs):
    """specs: (rule_id, uri, line, cwe_tag, level)."""
    rules, results = {}, []
    for rule_id, uri, line, tag, level in specs:
        rules[rule_id] = rule(rule_id, tags=(tag, "HIGH CONFIDENCE"), level=level)
        results.append(result(rule_id, uri=uri, line=line))
    return sarif.read_findings(doc(list(rules.values()), results))


def login(line=34, rule_id="javascript.sqli"):
    return findings((rule_id, "routes/login.ts", line, "CWE-89: Improper Neutralization", "error"))


def reader(text=LINE_TEXT):
    calls = []

    def read_line(path, line):
        calls.append((path, line))
        return text
    read_line.calls = calls
    return read_line


def run(client, fs, read_line=None, **kw):
    return ticket.process(fs, client, repo=REPO, commit=SHA, prefix="app/",
                          read_line=read_line or reader(), **kw)


# ---- the pieces

def test_fingerprint_is_file_line_and_cwe():
    assert ticket.fingerprint("app/routes/login.ts", 34, "CWE-89") == "app/routes/login.ts:34:CWE-89"


def test_line_hash_ignores_whitespace_and_is_short():
    assert ticket.line_hash("a b\t c") == ticket.line_hash("  abc \n")
    assert ticket.line_hash("abc") != ticket.line_hash("abd")
    assert len(ticket.line_hash("abc")) == 16


@pytest.mark.parametrize("level,label", [("error", "severity:high"), ("warning", "severity:medium"),
                                         ("note", "severity:low"), ("none", "severity:low")])
def test_severity_labels(level, label):
    assert ticket.severity_label(level) == label


def test_secret_findings_are_found_by_rule_id_or_cwe():
    by_rule = findings(("generic.secrets.security.detected-private-key", "k.ts", 1,
                        "CWE-321: Use of Hard-coded Cryptographic Key", "error"))[0]
    by_cwe = findings(("some.other.rule", "k.ts", 2, "CWE-798: Hard-coded Credentials", "error"))[0]
    by_name = findings(("secrets.thing", "k.ts", 3, "CWE-200: Exposure", "error"))[0]
    plain = login()[0]
    assert all(ticket.is_secret(f) for f in (by_rule, by_cwe, by_name))
    assert not ticket.is_secret(plain)


# ---- first run and second run

def test_first_run_creates_one_issue_per_finding():
    c = FakeClient()
    out = run(c, login())
    assert len(c.created) == 1 and out.created == 1 and out.found == 0
    issue = c.created[0]
    assert issue["title"] == "[high] CWE-89 in app/routes/login.ts"
    assert issue["labels"] == ["finding", "severity:high"]


def test_second_run_creates_nothing():
    c = FakeClient()
    run(c, login())
    out = run(c, login())
    assert len(c.created) == 1 and out.created == 0 and out.found == 1


def test_labels_are_ensured_only_when_creating():
    c = FakeClient()
    run(c, login())
    assert c.labels_ensured == ["finding", "severity:high"]
    c.labels_ensured.clear()
    run(c, login())
    assert c.labels_ensured == []


def test_two_rules_on_one_line_give_one_issue():
    fs = findings(("r.one", "routes/login.ts", 34, "CWE-89: x", "error"),
                  ("r.two", "routes/login.ts", 34, "CWE-89: x", "warning"))
    c = FakeClient()
    run(c, fs)
    assert len(c.created) == 1
    assert "`r.one`" in c.created[0]["body"] and "`r.two`" in c.created[0]["body"]


def test_a_closed_ticket_with_the_same_fingerprint_is_found_and_not_duplicated():
    c = FakeClient()
    run(c, login())
    c.issues[0]["state"] = "closed"
    out = run(c, login())
    assert len(c.created) == 1 and out.found == 1


def test_pull_requests_in_the_list_are_ignored():
    c = FakeClient()
    run(c, login())
    c.issues[0]["pull_request"] = {"url": "x"}
    out = run(c, login())
    assert out.created == 1 and len(c.issues) == 2


# ---- the body

def test_body_has_the_fields_the_spec_lists():
    c = FakeClient()
    run(c, login())
    body = c.created[0]["body"]
    assert "<!-- gr:fingerprint app/routes/login.ts:34:CWE-89 -->" in body
    assert f"<!-- gr:linehash {ticket.line_hash(LINE_TEXT)} -->" in body
    assert "CWE-89" in body and "high" in body and "`javascript.sqli`" in body
    assert f"https://github.com/{REPO}/blob/{SHA}/app/routes/login.ts#L34" in body
    assert body.index("## Verdict (M4-12)") < body.index("## Evidence (M2-8)")


def test_rule_message_text_and_snippets_never_reach_the_ticket():
    c = FakeClient()
    run(c, login())
    issue = c.created[0]
    assert SECRET_TEXT not in issue["body"] and SECRET_TEXT not in issue["title"]
    assert LINE_TEXT not in issue["body"]


def test_a_secret_finding_stores_no_line_text_and_no_hash():
    fs = findings(("generic.secrets.x", "ctf.key", 1, "CWE-798: Hard-coded Credentials", "error"))
    rl = reader("TOP-SECRET-LINE")
    c = FakeClient()
    run(c, fs, rl)
    body = c.created[0]["body"]
    assert "gr:linehash" not in body and "TOP-SECRET-LINE" not in body
    assert rl.calls == []          # the line is not even read
    assert "<!-- gr:fingerprint app/ctf.key:1:CWE-798 -->" in body


# ---- a moved line

def test_a_moved_line_with_the_same_hash_updates_the_open_ticket():
    c = FakeClient()
    run(c, login(34))
    out = run(c, login(40))
    assert len(c.created) == 1 and out.moved == 1 and out.created == 0
    body = c.issues[0]["body"]
    assert "<!-- gr:fingerprint app/routes/login.ts:40:CWE-89 -->" in body
    assert "app/routes/login.ts:34" not in body and "#L40" in body and "#L34" not in body
    assert ticket.line_hash(LINE_TEXT) in body


def test_a_moved_line_is_then_found_by_exact_match():
    c = FakeClient()
    run(c, login(34))
    run(c, login(40))
    out = run(c, login(40))
    assert out.found == 1 and out.moved == 0 and len(c.created) == 1


def test_a_different_line_with_a_different_hash_is_a_new_ticket():
    c = FakeClient()
    run(c, login(34), reader("one thing"))
    out = run(c, login(40), reader("another thing"))
    assert out.created == 1 and len(c.created) == 2


def test_a_moved_line_does_not_match_a_closed_ticket():
    c = FakeClient()
    run(c, login(34))
    c.issues[0]["state"] = "closed"
    out = run(c, login(40))
    assert out.created == 1


def test_a_moved_line_needs_the_same_cwe():
    c = FakeClient()
    run(c, login(34))
    other = findings(("r", "routes/login.ts", 40, "CWE-79: XSS", "error"))
    out = run(c, other)
    assert out.created == 1


def test_a_moved_secret_finding_gets_a_new_ticket():
    c = FakeClient()
    # An old ticket (made before the rule was known as a secret rule) that does carry a hash.
    run(c, findings(("r.plain", "k.ts", 1, "CWE-798: x", "error")), reader("same"), )
    old_body = c.issues[0]["body"]
    assert "gr:linehash" not in old_body    # CWE-798 is secret, so there was no hash anyway
    out = run(c, findings(("r.plain", "k.ts", 9, "CWE-798: x", "error")), reader("same"))
    assert out.created == 1 and out.moved == 0


def test_one_old_ticket_is_not_claimed_twice_in_a_run():
    c = FakeClient()
    run(c, login(34))
    fs = findings(("r", "routes/login.ts", 40, "CWE-89: x", "error"),
                  ("r", "routes/login.ts", 50, "CWE-89: x", "error"))
    out = run(c, fs)
    assert out.moved == 1 and out.created == 1


def test_a_ticket_without_markers_is_ignored():
    c = FakeClient([{"number": 1, "title": "hand-made", "body": "no markers", "labels": ["finding"],
                     "state": "open"}, {"number": 2, "title": "x", "body": None, "labels": ["finding"],
                                        "state": "open"}])
    out = run(c, login())
    assert out.created == 1


# ---- failures

def test_an_unreadable_source_line_stops_before_anything_is_created():
    def bad(path, line):
        raise TicketError(f"cannot read {path}")
    c = FakeClient()
    with pytest.raises(TicketError, match="cannot read"):
        run(c, login(), bad)
    assert c.created == [] and c.labels_ensured == []


def test_make_line_reader_reads_the_line_under_the_app_folder(tmp_path):
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "login.ts").write_text("one\ntwo\nthree\n")
    rl = ticket.make_line_reader(tmp_path)
    assert rl("routes/login.ts", 2) == "two"


@pytest.mark.parametrize("path,line", [("routes/missing.ts", 1), ("routes/login.ts", 99), ("routes/login.ts", 0)])
def test_make_line_reader_fails_clearly(tmp_path, path, line):
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "login.ts").write_text("one\n")
    with pytest.raises(TicketError, match="source line"):
        ticket.make_line_reader(tmp_path)(path, line)


def test_make_line_reader_refuses_to_leave_the_app_folder(tmp_path):
    with pytest.raises(TicketError, match="source line"):
        ticket.make_line_reader(tmp_path / "app")("../x", 1)


def test_filter_keeps_only_the_wanted_findings():
    fs = findings(("r", "routes/login.ts", 34, "CWE-89: x", "error"),
                  ("r", "routes/search.ts", 10, "CWE-89: x", "error"))
    assert [f.file for f in ticket.select(fs, ["routes/login.ts:CWE-89"])] == ["routes/login.ts"]
    assert len(ticket.select(fs, [])) == 2


def test_filter_that_matches_nothing_is_an_error():
    with pytest.raises(TicketError, match="no finding matches"):
        ticket.select(login(), ["routes/other.ts:CWE-89"])


def test_filter_must_look_like_file_and_cwe():
    with pytest.raises(TicketError, match="FILE:CWE"):
        ticket.select(login(), ["routes/login.ts"])


# ---- main

def write_sarif(tmp_path, lines=(34,)):
    d = doc([rule("javascript.sqli")], [result("javascript.sqli", line=n) for n in lines])
    p = tmp_path / "semgrep.sarif"
    p.write_text(json.dumps(d))
    app = tmp_path / "app" / "routes"
    app.mkdir(parents=True, exist_ok=True)
    (app / "login.ts").write_text("\n" * 33 + LINE_TEXT + "\n" + "x\n" * 10)
    return p, tmp_path / "app"


class Server:
    """A fake of the GitHub API behind the transport. Counts what is created."""

    def __init__(self):
        self.issues, self.posts, self.calls = [], 0, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers))
        if "/labels" in url:
            return 200, {"name": "x"}
        if method == "GET":
            return 200, (self.issues if "page=1" in url else [])
        if method == "POST":
            self.posts += 1
            data = json.loads(body)
            issue = {"number": len(self.issues) + 1, "state": "open", "labels": data["labels"],
                     "title": data["title"], "body": data["body"],
                     "html_url": f"https://github.com/{REPO}/issues/{len(self.issues) + 1}"}
            self.issues.append(issue)
            return 201, issue
        return 200, {}


def args(p, app, *more):
    return [str(p), "--app-dir", str(app), "--repo", REPO, "--commit", SHA,
            "--only", "routes/login.ts:CWE-89", *more]


def test_main_twice_creates_exactly_one_issue(tmp_path, capsys):
    p, app = write_sarif(tmp_path)
    server = Server()
    env = {"GITHUB_TOKEN": TOKEN}
    assert ticket.main(args(p, app), env=env, transport=server) == 0
    assert ticket.main(args(p, app), env=env, transport=server) == 0
    assert server.posts == 1 and len(server.issues) == 1
    out = capsys.readouterr()
    assert "created #1" in out.out and "found #1" in out.out
    assert TOKEN not in out.out + out.err


def test_main_takes_the_repo_from_the_environment(tmp_path):
    p, app = write_sarif(tmp_path)
    server = Server()
    argv = [str(p), "--app-dir", str(app), "--commit", SHA, "--only", "routes/login.ts:CWE-89"]
    assert ticket.main(argv, env={"GITHUB_TOKEN": TOKEN, "GITHUB_REPOSITORY": REPO}, transport=server) == 0
    assert any(f"/repos/{REPO}/" in c[1] for c in server.calls)


def test_main_without_a_token_exits_with_a_clear_message(tmp_path, capsys):
    p, app = write_sarif(tmp_path)

    def no_network(*a):
        raise AssertionError("no call may be made without a token")
    for env in ({}, {"GITHUB_TOKEN": ""}, {"GITHUB_TOKEN": "   "}):
        assert ticket.main(args(p, app), env=env, transport=no_network) == 1
    err = capsys.readouterr().err
    assert "GITHUB_TOKEN is not set" in err and ".env" in err


def test_main_on_a_github_error_exits_non_zero_without_the_token(tmp_path, capsys):
    p, app = write_sarif(tmp_path)

    def refuse(method, url, headers, body):
        return 401, {"message": f"Bad credentials {TOKEN}"}
    assert ticket.main(args(p, app), env={"GITHUB_TOKEN": TOKEN}, transport=refuse) == 1
    out = capsys.readouterr()
    assert "ticket: FAILED" in out.err and "401" in out.err
    assert TOKEN not in out.out + out.err


def test_main_creates_nothing_when_the_create_call_is_refused(tmp_path):
    p, app = write_sarif(tmp_path)
    server = Server()

    def refuse_post(method, url, headers, body):
        if method == "POST" and "/labels" not in url:
            return 403, {"message": "rate limit"}
        return server(method, url, headers, body)
    assert ticket.main(args(p, app), env={"GITHUB_TOKEN": TOKEN}, transport=refuse_post) == 1
    assert server.issues == []


@pytest.mark.parametrize("repo", ["", "noslash", "a/b/c"])
def test_main_rejects_a_bad_repo(tmp_path, repo, capsys):
    p, app = write_sarif(tmp_path)
    argv = [str(p), "--app-dir", str(app), "--repo", repo, "--commit", SHA]
    assert ticket.main(argv, env={"GITHUB_TOKEN": TOKEN}, transport=Server()) == 1
    assert "owner/name" in capsys.readouterr().err


def test_main_needs_a_commit(tmp_path, capsys):
    p, app = write_sarif(tmp_path)
    argv = [str(p), "--app-dir", str(app), "--repo", REPO]
    assert ticket.main(argv, env={"GITHUB_TOKEN": TOKEN}, transport=Server()) == 1
    assert "commit" in capsys.readouterr().err


def test_main_rejects_a_commit_that_is_not_a_full_sha(tmp_path, capsys):
    p, app = write_sarif(tmp_path)
    argv = [str(p), "--app-dir", str(app), "--repo", REPO, "--commit", "main"]
    assert ticket.main(argv, env={"GITHUB_TOKEN": TOKEN}, transport=Server()) == 1
    assert "40" in capsys.readouterr().err


def test_main_with_a_missing_sarif_file(tmp_path, capsys):
    _, app = write_sarif(tmp_path)
    assert ticket.main(args(tmp_path / "nope.sarif", app), env={"GITHUB_TOKEN": TOKEN}, transport=Server()) == 1
    assert "no SARIF file" in capsys.readouterr().err


def test_main_with_an_empty_scan_creates_nothing(tmp_path, capsys):
    p = tmp_path / "e.sarif"
    p.write_text(json.dumps(doc([rule("r")], [])))
    server = Server()
    assert ticket.main([str(p), "--app-dir", str(tmp_path), "--repo", REPO, "--commit", SHA],
                       env={"GITHUB_TOKEN": TOKEN}, transport=server) == 1
    assert server.posts == 0 and "no findings" in capsys.readouterr().err


def test_main_filter_that_matches_nothing_exits_non_zero(tmp_path, capsys):
    p, app = write_sarif(tmp_path)
    server = Server()
    argv = [str(p), "--app-dir", str(app), "--repo", REPO, "--commit", SHA, "--only", "routes/x.ts:CWE-89"]
    assert ticket.main(argv, env={"GITHUB_TOKEN": TOKEN}, transport=server) == 1
    assert server.posts == 0 and "no finding matches" in capsys.readouterr().err


def test_main_never_touches_dotenv(tmp_path, monkeypatch):
    # The token comes from the environment mapping only. A .env in the working folder is not read.
    (tmp_path / ".env").write_text(f"GITHUB_TOKEN={TOKEN}\n")
    monkeypatch.chdir(tmp_path)
    p, app = write_sarif(tmp_path)
    assert ticket.main(args(p, app), env={}, transport=Server()) == 1


def test_main_uses_the_process_environment_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    p, app = write_sarif(tmp_path)
    assert ticket.main(args(p, app), transport=Server()) == 1
