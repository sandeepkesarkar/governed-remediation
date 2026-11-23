"""A small GitHub issues client, standard library only.

The token goes in the Authorization header and nowhere else. Errors say the HTTP status
and a short reason. They never repeat the server's answer, and every message is scrubbed of
the token before it leaves this module.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
PER_PAGE = 100
MAX_PAGES = 50
TIMEOUT_SECONDS = 30
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_REASONS = {
    401: "the token was refused",
    403: "GitHub refused the request (check the token's permissions)",
    404: "not found (check the repository name and that the token can see it)",
    422: "GitHub rejected the data",
}


class GitHubError(Exception):
    """A GitHub call failed. The message never contains the token."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would forward the Authorization header to the redirect target. Refuse every redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GitHubError("GitHub sent a redirect. Check the repository name")


def urllib_transport(method, url, headers, body):
    """Send one request. Return (status, parsed JSON or None). Error statuses are returned, not raised."""
    if not url.startswith(API + "/"):
        raise GitHubError(f"refusing to call a URL that is not under {API}")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=TIMEOUT_SECONDS) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, (json.loads(raw) if raw else None)
    except ValueError:
        return status, None


class GitHubClient:
    def __init__(self, token, repo, transport=urllib_transport):
        if not _REPO.match(repo or ""):
            raise GitHubError("the repository must look like owner/name")
        self._token = token
        self.repo = repo
        self._transport = transport

    def _scrub(self, text):
        return str(text).replace(self._token, "***") if self._token else str(text)

    def _call(self, method, path, payload=None):
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "governed-remediation-ticket-step"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        try:
            return self._transport(method, f"{API}{path}", headers, body)
        except GitHubError:
            raise
        except Exception as e:  # network trouble: say so, without echoing details that may hold the token
            raise GitHubError(f"could not reach GitHub ({type(e).__name__})") from None

    def _fail(self, status, data, method, path):
        data_text = json.dumps(data) if data is not None else ""
        if status in (403, 429) and "rate limit" in data_text.lower():
            raise GitHubError(f"GitHub rate limit reached (HTTP {status}). Try again later")
        reason = _REASONS.get(status, "unexpected answer")
        raise GitHubError(self._scrub(f"GitHub {method} {path.split('?')[0]} failed: HTTP {status}, {reason}"))

    def _checked(self, method, path, payload=None):
        status, data = self._call(method, path, payload)
        if status not in (200, 201):
            self._fail(status, data, method, path)
        return data

    def list_issues(self, label):
        """All issues (open and closed) with the label. Pull requests are included by GitHub; callers skip them."""
        out = []
        for page in range(1, MAX_PAGES + 1):
            q = urllib.parse.urlencode({"labels": label, "state": "all", "per_page": PER_PAGE, "page": page})
            data = self._checked("GET", f"/repos/{self.repo}/issues?{q}")
            if not isinstance(data, list):
                raise GitHubError("GitHub gave an unexpected answer for the issue list")
            out.extend(data)
            if len(data) < PER_PAGE:
                return out
        raise GitHubError(f"too many issues to list (more than {MAX_PAGES * PER_PAGE})")

    def ensure_label(self, name, color):
        quoted = urllib.parse.quote(name, safe="")
        path = f"/repos/{self.repo}/labels/{quoted}"
        status, data = self._call("GET", path)
        if status == 200:
            return
        if status != 404:
            self._fail(status, data, "GET", path)
        self._checked("POST", f"/repos/{self.repo}/labels", {"name": name, "color": color})

    def create_issue(self, title, body, labels):
        return self._checked("POST", f"/repos/{self.repo}/issues", {"title": title, "body": body, "labels": labels})

    def update_issue(self, number, body):
        return self._checked("PATCH", f"/repos/{self.repo}/issues/{int(number)}", {"body": body})
