"""A small GitHub client for issues, branches and pull requests, standard library only.

Shared by the ticket step (issues) and the fix step (issues, commits through the Git data API,
branches and pull requests). Each caller passes its own token and its own user agent.

The token goes in the Authorization header and nowhere else. Errors say the HTTP status
and a short reason. They never repeat the server's answer, and every message is scrubbed of
the token before it leaves this module.
"""
import base64
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
_SHA = re.compile(r"^[0-9a-f]{40}$")
# A conservative branch name: no spaces, no "..", no leading dash or dot, no trailing slash.
_BRANCH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]{0,199}$")

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
    def __init__(self, token, repo, transport=urllib_transport, user_agent="governed-remediation-ticket-step"):
        if not _REPO.match(repo or ""):
            raise GitHubError("the repository must look like owner/name")
        self._token = token
        self.repo = repo
        self._transport = transport
        self._user_agent = user_agent

    def _scrub(self, text):
        return str(text).replace(self._token, "***") if self._token else str(text)

    def _call(self, method, path, payload=None):
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": self._user_agent}
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

    # ---- the fix step: read an issue, make one commit on a new branch, open a pull request ----

    def get_issue(self, number):
        return self._checked("GET", f"/repos/{self.repo}/issues/{int(number)}")

    @staticmethod
    def _check_branch(name):
        if not isinstance(name, str) or not _BRANCH.match(name) or ".." in name or name.endswith(("/", ".")) \
                or any(c in name for c in "~^:?*[\\@{ "):
            raise GitHubError("the branch name is not acceptable")

    @staticmethod
    def _need_sha(data, what="answer"):
        sha = data.get("sha") if isinstance(data, dict) else None
        if not isinstance(sha, str) or not _SHA.match(sha):
            raise GitHubError(f"GitHub gave an unexpected {what}")
        return sha

    def get_branch_sha(self, branch):
        """The commit SHA at the tip of a branch, or None if the branch does not exist."""
        self._check_branch(branch)
        path = f"/repos/{self.repo}/git/ref/heads/{branch}"
        status, data = self._call("GET", path)
        if status == 404:
            return None
        if status != 200:
            self._fail(status, data, "GET", path)
        sha = ((data or {}).get("object") or {}).get("sha") if isinstance(data, dict) else None
        if not isinstance(sha, str) or not _SHA.match(sha):
            raise GitHubError("GitHub gave an unexpected answer for the branch")
        return sha

    def get_commit_tree_sha(self, commit_sha):
        if not _SHA.match(commit_sha or ""):
            raise GitHubError("the commit SHA must be 40 lower-case hex characters")
        data = self._checked("GET", f"/repos/{self.repo}/git/commits/{commit_sha}")
        tree = (data.get("tree") if isinstance(data, dict) else None) or {}
        return self._need_sha(tree, "answer for the commit")

    def create_blob(self, content):
        data = self._checked("POST", f"/repos/{self.repo}/git/blobs",
                             {"content": base64.b64encode(content).decode(), "encoding": "base64"})
        return self._need_sha(data, "answer for the file")

    def create_tree(self, base_tree, files):
        """files: (path, blob_sha) pairs. Every file is a regular, non-executable file."""
        entries = [{"path": p, "mode": "100644", "type": "blob", "sha": sha} for p, sha in files]
        data = self._checked("POST", f"/repos/{self.repo}/git/trees", {"base_tree": base_tree, "tree": entries})
        return self._need_sha(data, "answer for the tree")

    def create_commit(self, message, tree_sha, parent_sha):
        data = self._checked("POST", f"/repos/{self.repo}/git/commits",
                             {"message": message, "tree": tree_sha, "parents": [parent_sha]})
        return self._need_sha(data, "answer for the commit")

    def create_branch(self, branch, sha):
        self._check_branch(branch)
        return self._checked("POST", f"/repos/{self.repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha})

    def create_pull_request(self, title, body, head, base):
        return self._checked("POST", f"/repos/{self.repo}/pulls",
                             {"title": title, "body": body, "head": head, "base": base})

    def list_pull_requests_by_head(self, branch):
        """Pull requests (any state) whose head is the branch in this repository."""
        self._check_branch(branch)
        owner = self.repo.split("/")[0]
        q = urllib.parse.urlencode({"head": f"{owner}:{branch}", "state": "all", "per_page": PER_PAGE})
        data = self._checked("GET", f"/repos/{self.repo}/pulls?{q}")
        if not isinstance(data, list):
            raise GitHubError("GitHub gave an unexpected answer for the pull request list")
        return data

    # ---- the verify step: read a pull request, post or update one evidence comment ----

    def get_pull_request(self, number):
        return self._checked("GET", f"/repos/{self.repo}/pulls/{int(number)}")

    def list_issue_comments(self, number):
        """All comments on an issue or pull request (a pull request is an issue for comments)."""
        out = []
        for page in range(1, MAX_PAGES + 1):
            q = urllib.parse.urlencode({"per_page": PER_PAGE, "page": page})
            data = self._checked("GET", f"/repos/{self.repo}/issues/{int(number)}/comments?{q}")
            if not isinstance(data, list):
                raise GitHubError("GitHub gave an unexpected answer for the comment list")
            out.extend(data)
            if len(data) < PER_PAGE:
                return out
        raise GitHubError(f"too many comments to list (more than {MAX_PAGES * PER_PAGE})")

    def create_issue_comment(self, number, body):
        return self._checked("POST", f"/repos/{self.repo}/issues/{int(number)}/comments", {"body": body})

    def update_issue_comment(self, comment_id, body):
        return self._checked("PATCH", f"/repos/{self.repo}/issues/comments/{int(comment_id)}", {"body": body})
