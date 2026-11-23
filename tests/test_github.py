"""Tests for the GitHub client. The transport is faked: no network, no token.

The token below is a made-up marker. Tests check that it never comes out in an error.
"""
import io
import json
import urllib.error

import pytest

from agents.ticket_agent import github
from agents.ticket_agent.github import GitHubClient, GitHubError

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


# The default transport (urllib), with urlopen faked.

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


def test_default_transport_returns_status_and_json(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["req"], seen["timeout"] = req, timeout
        return FakeResponse(200, b'[{"number": 1}]')
    monkeypatch.setattr(github.urllib.request, "urlopen", fake_urlopen)
    status, data = github.urllib_transport("GET", "https://api.github.com/x", {"A": "b"}, None)
    assert (status, data) == (200, [{"number": 1}])
    assert seen["req"].get_method() == "GET" and seen["timeout"] == 30


def test_default_transport_handles_an_empty_body(monkeypatch):
    monkeypatch.setattr(github.urllib.request, "urlopen", lambda req, timeout=None: FakeResponse(204, b""))
    assert github.urllib_transport("PATCH", "https://api.github.com/x", {}, b"{}") == (204, None)


def test_default_transport_turns_an_http_error_into_a_status(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"message": "no"}'))
    monkeypatch.setattr(github.urllib.request, "urlopen", fake_urlopen)
    assert github.urllib_transport("GET", "https://api.github.com/x", {}, None) == (403, {"message": "no"})


def test_default_transport_copes_with_a_body_that_is_not_json(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 502, "Bad", {}, io.BytesIO(b"<html>"))
    monkeypatch.setattr(github.urllib.request, "urlopen", fake_urlopen)
    assert github.urllib_transport("GET", "https://api.github.com/x", {}, None) == (502, None)


def test_default_transport_refuses_a_non_github_url():
    with pytest.raises(GitHubError, match="https://api.github.com"):
        github.urllib_transport("GET", "http://example.com/x", {}, None)
