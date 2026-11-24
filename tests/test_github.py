"""Tests for the GitHub client. The transport is faked: no network, no token.

The token below is a made-up marker. Tests check that it never comes out in an error.
"""
import io
import json
import urllib.error

import pytest

from agents.common import github
from agents.common.github import GitHubClient, GitHubError

TOKEN = "ghp_FAKETOKENMARKER1234567890"


class Transport:
    """Records calls and answers from a queue of (status, json) pairs."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        status, data = self.answers.pop(0)
        return status, data


def client(*answers):
    t = Transport(*answers)
    return GitHubClient(TOKEN, "o/r", transport=t), t


def test_every_call_sends_the_token_in_the_header_only():
    c, t = client((200, []))
    c.list_issues("finding")
    method, url, headers, _ = t.calls[0]
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in url


def test_list_issues_asks_for_all_states_and_the_label_and_follows_pages():
    page1 = [{"number": n} for n in range(100)]
    c, t = client((200, page1), (200, [{"number": 100}]))
    issues = c.list_issues("finding")
    assert len(issues) == 101
    assert t.calls[0][1].startswith("https://api.github.com/repos/o/r/issues?")
    assert "labels=finding" in t.calls[0][1] and "state=all" in t.calls[0][1]
    assert "page=1" in t.calls[0][1] and "page=2" in t.calls[1][1]


def test_list_issues_stops_at_a_page_limit():
    full = [{"number": n} for n in range(100)]
    c, t = client(*[(200, full)] * 60)
    with pytest.raises(GitHubError, match="too many"):
        c.list_issues("finding")


def test_create_issue_posts_title_body_and_labels():
    c, t = client((201, {"number": 7, "html_url": "u"}))
    out = c.create_issue("T", "B", ["finding", "severity:high"])
    assert out["number"] == 7
    method, url, _, body = t.calls[0]
    assert (method, url) == ("POST", "https://api.github.com/repos/o/r/issues")
    assert json.loads(body) == {"title": "T", "body": "B", "labels": ["finding", "severity:high"]}


def test_update_issue_patches_the_body():
    c, t = client((200, {"number": 7}))
    c.update_issue(7, "new body")
    method, url, _, body = t.calls[0]
    assert (method, url) == ("PATCH", "https://api.github.com/repos/o/r/issues/7")
    assert json.loads(body) == {"body": "new body"}


def test_ensure_label_does_nothing_when_the_label_exists():
    c, t = client((200, {"name": "finding"}))
    c.ensure_label("finding", "d73a4a")
    assert [x[0] for x in t.calls] == ["GET"]


def test_ensure_label_creates_a_missing_label():
    c, t = client((404, {"message": "Not Found"}), (201, {"name": "finding"}))
    c.ensure_label("severity:high", "b60205")
    assert [x[0] for x in t.calls] == ["GET", "POST"]
    assert "severity%3Ahigh" in t.calls[0][1]
    assert json.loads(t.calls[1][3]) == {"name": "severity:high", "color": "b60205"}


def test_ensure_label_fails_on_an_error_other_than_not_found():
    c, _ = client((500, None))
    with pytest.raises(GitHubError, match="500"):
        c.ensure_label("finding", "d73a4a")


def test_a_github_error_from_the_transport_passes_through():
    def refuse(*a):
        raise GitHubError("refused")
    with pytest.raises(GitHubError, match="refused"):
        GitHubClient(TOKEN, "o/r", transport=refuse).list_issues("finding")


@pytest.mark.parametrize("status", [401, 403, 404, 422, 500])
def test_an_error_status_raises_with_the_status_and_without_the_token(status):
    # The server answer echoes the token on purpose. It must not reach the message.
    c, _ = client((status, {"message": f"bad credentials {TOKEN}"}))
    with pytest.raises(GitHubError) as e:
        c.create_issue("T", "B", [])
    assert str(status) in str(e.value)
    assert TOKEN not in str(e.value)


def test_a_rate_limit_is_named():
    c, _ = client((403, {"message": "API rate limit exceeded"}))
    with pytest.raises(GitHubError, match="rate limit"):
        c.list_issues("finding")


def test_a_transport_failure_is_scrubbed():
    def boom(*a):
        raise OSError(f"connection failed for {TOKEN}")
    c = GitHubClient(TOKEN, "o/r", transport=boom)
    with pytest.raises(GitHubError) as e:
        c.list_issues("finding")
    assert TOKEN not in str(e.value)
    assert "could not reach GitHub" in str(e.value)


def test_an_answer_that_is_not_the_expected_shape_is_an_error():
    c, _ = client((200, {"not": "a list"}))
    with pytest.raises(GitHubError, match="unexpected"):
        c.list_issues("finding")


def test_a_bad_repo_name_is_rejected():
    with pytest.raises(GitHubError, match="owner/name"):
        GitHubClient(TOKEN, "not-a-repo")


# The default transport (urllib), with the opener faked.

class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self._data = payload

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def use_opener(monkeypatch, open_function):
    """Make the default transport use open_function(req, timeout=...) instead of the network."""
    class Opener:
        def open(self, req, timeout=None):
            return open_function(req, timeout=timeout)
    monkeypatch.setattr(github.urllib.request, "build_opener", lambda *handlers: Opener())


def test_default_transport_returns_status_and_json(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["req"], seen["timeout"] = req, timeout
        return FakeResponse(200, b'[{"number": 1}]')
    use_opener(monkeypatch, fake_urlopen)
    status, data = github.urllib_transport("GET", "https://api.github.com/x", {"A": "b"}, None)
    assert (status, data) == (200, [{"number": 1}])
    assert seen["req"].get_method() == "GET" and seen["timeout"] == 30


def test_default_transport_handles_an_empty_body(monkeypatch):
    use_opener(monkeypatch, lambda req, timeout=None: FakeResponse(204, b""))
    assert github.urllib_transport("PATCH", "https://api.github.com/x", {}, b"{}") == (204, None)


def test_default_transport_turns_an_http_error_into_a_status(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"message": "no"}'))
    use_opener(monkeypatch, fake_urlopen)
    assert github.urllib_transport("GET", "https://api.github.com/x", {}, None) == (403, {"message": "no"})


def test_default_transport_copes_with_a_body_that_is_not_json(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 502, "Bad", {}, io.BytesIO(b"<html>"))
    use_opener(monkeypatch, fake_urlopen)
    assert github.urllib_transport("GET", "https://api.github.com/x", {}, None) == (502, None)


def test_default_transport_refuses_a_non_github_url():
    with pytest.raises(GitHubError, match="https://api.github.com"):
        github.urllib_transport("GET", "http://example.com/x", {}, None)


# Redirects: urllib would forward the Authorization header to the new address.

@pytest.mark.parametrize("code", [301, 302, 307, 308])
def test_a_redirect_is_refused_and_the_message_has_no_token(code):
    handler = github.NoRedirect()
    req = github.urllib.request.Request("https://api.github.com/repos/o/r/issues",
                                        headers={"Authorization": f"Bearer {TOKEN}"})
    with pytest.raises(GitHubError) as e:
        handler.redirect_request(req, None, code, "Moved", {}, f"https://evil.example/{TOKEN}")
    assert str(e.value) == "GitHub sent a redirect. Check the repository name"
    assert TOKEN not in str(e.value)


def test_the_default_transport_uses_an_opener_that_refuses_redirects(monkeypatch):
    seen = {}

    class O:
        def open(self, req, timeout=None):
            seen["timeout"] = timeout
            return FakeResponse(200, b"[]")

    def build(*handlers):
        seen["handlers"] = handlers
        return O()
    monkeypatch.setattr(github.urllib.request, "build_opener", build)
    assert github.urllib_transport("GET", "https://api.github.com/x", {}, None) == (200, [])
    assert github.NoRedirect in seen["handlers"]


@pytest.mark.parametrize("code", [301, 307])
def test_a_real_redirect_through_urllib_is_refused(code):
    """A local server on 127.0.0.1 answers with a redirect. The real urllib machinery must not follow it."""
    import http.server
    import threading

    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append((self.path, self.headers.get("Authorization")))
            if self.path == "/start":
                self.send_response(code)
                self.send_header("Location", "/elsewhere")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = github.urllib.request.Request(f"http://127.0.0.1:{server.server_port}/start",
                                            headers={"Authorization": f"Bearer {TOKEN}"})
        with pytest.raises(GitHubError) as e:
            github.urllib.request.build_opener(github.NoRedirect).open(req, timeout=5)
    finally:
        server.shutdown()
        server.server_close()
    assert TOKEN not in str(e.value)
    assert [h[0] for h in hits] == ["/start"]      # the redirect target was never requested


# ---- calls added for the fix step (M2-7) ----

def test_the_user_agent_names_the_step_that_uses_the_client():
    t = Transport((200, []))
    GitHubClient(TOKEN, "o/r", transport=t, user_agent="governed-remediation-fix-step").list_issues("x")
    assert t.calls[0][2]["User-Agent"] == "governed-remediation-fix-step"


def test_get_issue_reads_one_issue():
    c, t = client((200, {"number": 3}))
    assert c.get_issue(3) == {"number": 3}
    assert t.calls[0][:2] == ("GET", "https://api.github.com/repos/o/r/issues/3")


def test_get_branch_sha_returns_the_commit_sha():
    c, t = client((200, {"object": {"sha": "a" * 40}}))
    assert c.get_branch_sha("main") == "a" * 40
    assert t.calls[0][1] == "https://api.github.com/repos/o/r/git/ref/heads/main"


def test_get_branch_sha_returns_none_for_a_missing_branch():
    c, _ = client((404, {"message": "Not Found"}))
    assert c.get_branch_sha("fix/x") is None


def test_get_branch_sha_fails_on_other_errors():
    c, _ = client((403, {}))
    with pytest.raises(GitHubError, match="HTTP 403"):
        c.get_branch_sha("main")


def test_get_branch_sha_rejects_an_odd_answer():
    c, _ = client((200, {"object": {}}))
    with pytest.raises(GitHubError, match="unexpected"):
        c.get_branch_sha("main")


@pytest.mark.parametrize("name", ["", "-x", "a b", "a..b", "x/", "/x", "a\nb", "x" * 201, "a~b", "a:b", ".hidden/x"])
def test_branch_names_that_could_confuse_a_url_or_ref_are_refused(name):
    c, _ = client()
    with pytest.raises(GitHubError, match="branch name"):
        c.get_branch_sha(name)


def test_get_commit_tree_sha():
    c, t = client((200, {"tree": {"sha": "b" * 40}}))
    assert c.get_commit_tree_sha("a" * 40) == "b" * 40
    assert t.calls[0][1] == f"https://api.github.com/repos/o/r/git/commits/{'a' * 40}"


def test_get_commit_tree_sha_rejects_a_bad_sha_and_an_odd_answer():
    c, _ = client((200, {"tree": {}}))
    with pytest.raises(GitHubError, match="commit SHA"):
        c.get_commit_tree_sha("not-a-sha")
    with pytest.raises(GitHubError, match="unexpected"):
        c.get_commit_tree_sha("a" * 40)


def test_create_blob_sends_base64_and_returns_the_sha():
    c, t = client((201, {"sha": "c" * 40}))
    assert c.create_blob(b"hello") == "c" * 40
    body = json.loads(t.calls[0][3])
    assert body == {"content": "aGVsbG8=", "encoding": "base64"}
    assert t.calls[0][1].endswith("/git/blobs")


def test_create_tree_commit_and_ref():
    c, t = client((201, {"sha": "d" * 40}), (201, {"sha": "e" * 40}), (201, {"ref": "refs/heads/fix/x"}))
    tree = c.create_tree("b" * 40, [("app/a.ts", "c" * 40)])
    assert tree == "d" * 40
    assert json.loads(t.calls[0][3]) == {
        "base_tree": "b" * 40, "tree": [{"path": "app/a.ts", "mode": "100644", "type": "blob", "sha": "c" * 40}]}
    commit = c.create_commit("msg", "d" * 40, "a" * 40)
    assert commit == "e" * 40
    assert json.loads(t.calls[1][3]) == {"message": "msg", "tree": "d" * 40, "parents": ["a" * 40]}
    c.create_branch("fix/x", "e" * 40)
    assert json.loads(t.calls[2][3]) == {"ref": "refs/heads/fix/x", "sha": "e" * 40}


def test_create_calls_reject_an_answer_without_a_sha():
    c, _ = client((201, {}), (201, {}), (201, {}))
    with pytest.raises(GitHubError, match="unexpected"):
        c.create_blob(b"x")
    with pytest.raises(GitHubError, match="unexpected"):
        c.create_tree("b" * 40, [("app/a.ts", "c" * 40)])
    with pytest.raises(GitHubError, match="unexpected"):
        c.create_commit("m", "d" * 40, "a" * 40)


def test_create_pull_request_and_list_by_head():
    c, t = client((201, {"number": 9, "html_url": "u"}), (200, [{"number": 9}]))
    pr = c.create_pull_request("T", "B", head="fix/x", base="main")
    assert pr["number"] == 9
    assert json.loads(t.calls[0][3]) == {"title": "T", "body": "B", "head": "fix/x", "base": "main"}
    assert c.list_pull_requests_by_head("fix/x") == [{"number": 9}]
    assert "head=o%3Afix%2Fx" in t.calls[1][1] and "state=all" in t.calls[1][1]


def test_list_pull_requests_rejects_an_odd_answer():
    c, _ = client((200, {"x": 1}))
    with pytest.raises(GitHubError, match="unexpected"):
        c.list_pull_requests_by_head("fix/x")


def test_the_token_never_appears_in_a_url_or_body_of_the_new_calls():
    c, t = client((201, {"sha": "c" * 40}), (201, {"number": 1}))
    c.create_blob(b"x")
    c.create_pull_request("T", "B", head="fix/x", base="main")
    for _, url, _, body in t.calls:
        assert TOKEN not in url and TOKEN.encode() not in (body or b"")
