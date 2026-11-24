"""Step "fix", part 3: put the agent's files on a branch and open the pull request (M2-7).

This is a plain script. No model is involved, and it never talks to the sandbox. It reads a tar file the
launcher copied out of the sandbox, and it never unpacks that tar onto disk: it reads the members in memory,
checks them, and sends the few allowed files to GitHub through the API (blobs, tree, commit, branch, pull
request). No git command and no git credentials are needed.

It holds the fix token (GITHUB_FIX_TOKEN: Contents and Pull requests, write). The agent never sees it.

The comparison base is origin/main's own files, exported by the launcher with "git archive" into --base-dir, not the
working folder. --base-sha is the commit they came from. The step stops if GitHub's main is not that commit.

Checks before anything is written:
  - the tar holds only plain files and folders, with safe paths and sane sizes
  - only files in routes/, lib/, models/ and test/server/ differ from the base (a few runtime noise files and the
    agent's own .git folder are ignored), nothing is deleted, and there are at most 10 changed files, all text
  - a file byte-identical to the base is never a change, whatever its size. A new or changed file is held to
    200 KB, whatever its path
  - the target file changed, and the regression test is present
  - neither the branch nor a pull request for it exists yet, so a second run never makes a second pull request

Command line (used by scripts/fix.sh):
    python -m agents.fixer_agent.publish --repo OWNER/NAME --task task.json --tree tree.tar --base-dir BASE --base-sha SHA
"""
import argparse
import hashlib
import json
import os
import sys
import tarfile
from pathlib import Path

from agents.common.github import GitHubClient, GitHubError
from agents.fixer_agent import sanity

TOKEN_VARIABLE = "GITHUB_FIX_TOKEN"   # a different variable from the ticket token on purpose
ALLOWED_PREFIXES = ("routes/", "lib/", "models/", "test/server/")
IGNORED_PREFIXES = (".git/", "node_modules/", "logs/", "coverage/", ".nyc_output/", "build/", "dist/", "tmp/",
                    "data/juiceshop", "ftp/", "uploads/")
IGNORED_NAMES = {"package-lock.json"}
MAX_FILE_BYTES = 200_000          # the cap for a new or changed file
MAX_HASHED_BYTES = 100_000_000    # a larger file than this is refused outright, even to compare it
MAX_MEMBERS = 20_000
MAX_FILES = 10
BASE_BRANCH = "main"


class PublishError(Exception):
    """The step stops. The message says why, without tokens."""


class LargeFile:
    """A file above the size cap. Only its size and hash are kept, to compare it with the base."""

    def __init__(self, size, sha256):
        self.size, self.sha256 = size, sha256


def is_ignored(rel):
    return rel in IGNORED_NAMES or rel.startswith(IGNORED_PREFIXES)


def read_tree(tar_path):
    """{relative path: bytes} for every plain file worth looking at. Nothing is written to disk."""
    files = {}
    try:
        with tarfile.open(tar_path, "r:") as tf:
            for count, member in enumerate(tf, 1):
                if count > MAX_MEMBERS:
                    raise PublishError("the tar has too many entries")
                name = member.name
                while name.startswith("./"):
                    name = name[2:]
                if name in ("", "."):
                    continue
                if name.startswith("/") or ".." in name.split("/") or "\\" in name or "\x00" in name:
                    raise PublishError("the tar has an unsafe path")
                if is_ignored(name):
                    continue
                if member.isdir():
                    continue
                if not member.isreg():
                    raise PublishError(f"the tar has an entry that is not a plain file ({name})")
                if member.size > MAX_HASHED_BYTES:
                    raise PublishError(f"a file in the tar is too large ({name})")
                if member.size > MAX_FILE_BYTES:
                    digest = hashlib.sha256()
                    with tf.extractfile(member) as f:
                        for chunk in iter(lambda: f.read(1 << 20), b""):
                            digest.update(chunk)
                    files[name] = LargeFile(member.size, digest.hexdigest())
                else:
                    files[name] = tf.extractfile(member).read()
    except tarfile.TarError:
        raise PublishError("cannot read the tar file") from None
    return files


def _base_path(base_dir, rel):
    root = Path(base_dir).resolve()
    target = (root / rel).resolve()
    if root not in target.parents:
        raise PublishError("a path leaves the base folder")
    return target


def _same_as_base(base_dir, rel, data):
    """True only if the base has this exact path with exactly these bytes."""
    target = _base_path(base_dir, rel)
    if not target.is_file():
        return False
    if isinstance(data, LargeFile):
        if target.stat().st_size != data.size:
            return False
        digest = hashlib.sha256()
        with open(target, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest() == data.sha256
    return target.read_bytes() == data


def changed_files(tree, base_dir, task):
    """{path: bytes} to commit. Raises PublishError if the result breaks any rule."""
    changes = {}
    for rel, data in sorted(tree.items()):
        if is_ignored(rel) or _same_as_base(base_dir, rel, data):
            continue
        if isinstance(data, LargeFile):
            raise PublishError(f"a new or changed file is too large ({rel}, the limit is {MAX_FILE_BYTES} bytes)")
        if not rel.startswith(ALLOWED_PREFIXES):
            raise PublishError(f"the agent changed a file outside the allowed folders ({rel})")
        changes[rel] = data

    root = Path(base_dir).resolve()
    for prefix in ALLOWED_PREFIXES:
        folder = root / prefix
        for f in sorted(folder.rglob("*")) if folder.is_dir() else []:
            rel = f.relative_to(root).as_posix()
            if f.is_file() and rel not in tree and not is_ignored(rel):
                raise PublishError(f"the agent deleted a file ({rel})")

    if task["rel_file"] not in changes:
        raise PublishError(f"the target file {task['rel_file']} was not changed")
    if sanity.SPEC not in changes:
        raise PublishError(f"the regression test {sanity.SPEC} is missing")
    if len(changes) > MAX_FILES:
        raise PublishError(f"too many changed files ({len(changes)}, the limit is {MAX_FILES})")
    for rel, data in changes.items():
        if len(data) > MAX_FILE_BYTES:
            raise PublishError(f"a new or changed file is too large ({rel}, the limit is {MAX_FILE_BYTES} bytes)")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise PublishError(f"a changed file is not text ({rel})") from None
        if b"\x00" in data:
            raise PublishError(f"a changed file is not text ({rel})")
    return changes


def build_body(task, paths, metrics, sanity_result):
    m = metrics or {}
    s = sanity_result or {}
    cost = f"${m['cost_usd']:.4f}" if isinstance(m.get("cost_usd"), (int, float)) else "unknown"
    lines = [
        f"Closes #{task['issue']}",
        "",
        f"Proposed fix for {task['cwe']} in `{task['file']}` (line {task['line']}). "
        "A script opened this pull request from files an AI agent (OpenHands) wrote in a throwaway copy of `app/`.",
        "",
        "**Not yet verified.** The verify step (M2-8) has not run. **Do not merge this pull request** until it has "
        "posted its evidence: tests pass, the finding is gone, and the attack fails.",
        "",
        "## Files changed",
        *[f"- `app/{p}`" for p in paths],
        "",
        "## Checks run so far (a sanity check, not verification)",
        f"- The regression test and two existing Juice Shop specs ran in the sandbox: "
        f"{s.get('passing', 'unknown')} passing, {s.get('failing', 'unknown')} failing.",
        "",
        "## Run",
        f"- Model: {m.get('model', 'unknown')}",
        f"- Cost: {cost} (tokens in {m.get('input_tokens', 'unknown')}, out {m.get('output_tokens', 'unknown')})",
        f"- Caps: ${m.get('max_budget', 'unknown')} and {m.get('max_iterations', 'unknown')} steps, set in OpenHands",
        f"- Budget cap hit: {m.get('budget_cap_hit', 'unknown')}. Iteration cap hit: {m.get('iteration_cap_hit', 'unknown')}",
    ]
    return "\n".join(lines) + "\n"


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def publish(client, task, changes, body, model, expected_base_sha):
    """Branch, commit, pull request. Returns the pull request answer."""
    branch = task["branch"]
    if client.get_branch_sha(branch) is not None:
        raise PublishError(f"the branch {branch} already exists. Nothing was changed")
    if client.list_pull_requests_by_head(branch):
        raise PublishError(f"a pull request for {branch} already exists. Nothing was changed")

    base_sha = client.get_branch_sha(BASE_BRANCH)
    if base_sha is None:
        raise PublishError(f"the base branch {BASE_BRANCH} was not found")
    if base_sha != expected_base_sha:
        raise PublishError(f"{BASE_BRANCH} has moved since the base files were exported. Nothing was changed. "
                           "Run the step again")
    tree_sha = client.create_tree(client.get_commit_tree_sha(base_sha),
                                  [(f"app/{p}", client.create_blob(d)) for p, d in sorted(changes.items())])
    message = (f"{task['title']}\n\nWritten by the OpenHands fixer ({model}) from issue #{task['issue']}. "
               "Not yet verified (M2-8).")
    commit_sha = client.create_commit(message, tree_sha, base_sha)
    client.create_branch(branch, commit_sha)
    try:
        return client.create_pull_request(task["title"], body, head=branch, base=BASE_BRANCH)
    except GitHubError as e:
        raise PublishError(f"the branch {branch} was created but no pull request was opened ({e}). "
                           "Delete the branch, or open the pull request by hand") from None


def main(argv=None, env=None, transport=None):
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description="Push the agent's files to a branch and open a pull request.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--base-dir", required=True, help="origin/main's app/ files, exported with git archive")
    ap.add_argument("--base-sha", required=True, help="the commit the base files came from")
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--sanity", required=True)
    ap.add_argument("--pr-out", required=True)
    args = ap.parse_args(argv)

    token = (env.get(TOKEN_VARIABLE) or "").strip()

    def fail(message):
        print(f"publish: FAILED: {message.replace(token, '***') if token else message}", file=sys.stderr)
        return 1

    if not token:
        return fail(f"{TOKEN_VARIABLE} is not set. Put it in .env (names are in .env.example)")
    try:
        task = _json(args.task)
        if not isinstance(task, dict):
            raise PublishError("cannot read the task file")
        metrics, sanity_result = _json(args.metrics), _json(args.sanity)
        changes = changed_files(read_tree(args.tree), args.base_dir, task)
        body = build_body(task, sorted(changes), metrics if isinstance(metrics, dict) else None,
                          sanity_result if isinstance(sanity_result, dict) else None)
        client = GitHubClient(token, args.repo, user_agent="governed-remediation-fix-step",
                              **({"transport": transport} if transport else {}))
        pr = publish(client, task, changes, body, (metrics or {}).get("model", "unknown")
                     if isinstance(metrics, dict) else "unknown", args.base_sha)
    except (PublishError, GitHubError) as e:
        return fail(str(e))
    Path(args.pr_out).write_text(json.dumps({"number": pr["number"], "url": pr["html_url"],
                                             "branch": task["branch"]}, indent=2) + "\n", encoding="utf-8")
    print(f"publish: opened pull request #{pr['number']} {pr['html_url']} (branch {task['branch']}, "
          f"{len(changes)} files). Not merged. It waits for the verify step")
    return 0


if __name__ == "__main__":
    sys.exit(main())
