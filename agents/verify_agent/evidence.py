"""Step "verify", the evidence (plan M2-8). No model is involved anywhere in this step.

scripts/verify.sh does the work in containers and leaves plain files in one folder (out/verify): exit codes
(*.rc), test output (*.txt), the re-scan SARIF and the exploit result. This module reads those files, decides
what each one proves, writes one comment and posts it on the pull request. It never merges and never decides
anything. It only reports. A check that did not run or could not finish is reported as such, never as a pass.

Four checks (each ends as pass, fail, warn, error or not run):
  1. regression test: the new spec fails on main's unfixed code and passes on the pull request's code
  2. test suite: the server specs on the pull request's code, compared with main's code when something fails
  3. re-scan: Semgrep on the pull request's app/ no longer reports the finding recorded on the issue
  4. exploit: the real login exploit fails against a throwaway build of the pull request, and a real login works

The comment carries a hidden marker. A second run updates that comment and never adds another.
The re-scan check keeps only file, line and CWE. It never copies Semgrep message text.

The token is GITHUB_VERIFY_TOKEN (Issues and Pull requests write). It reads the pull request and the issue, and posts
both comments: the full evidence on the pull request, and a short linked summary on the issue (spec section 4).

Command line (used by scripts/verify.sh):
    python -m agents.verify_agent.evidence pr-info --repo O/N --pr N --dir DIR
    python -m agents.verify_agent.evidence scope --dir DIR
    python -m agents.verify_agent.evidence report --dir DIR --repo O/N --pr N [--post]
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from agents.common.github import GitHubClient, GitHubError
from agents.ticket_agent import sarif, ticket

TOKEN_VARIABLE = "GITHUB_VERIFY_TOKEN"   # Issues and Pull requests write, nothing else. Not the ticket or fix token
MARKER = "<!-- gr:evidence -->"
SUMMARY_MARKER = "<!-- gr:evidence-summary -->"   # the short note on the ticket
ALLOWED_PREFIXES = ("app/routes/", "app/lib/", "app/models/", "app/test/server/")
TEST_PREFIX = "app/test/"
MAX_FILES = 10
MAX_COMMENT_CHARS = 60_000        # GitHub's limit is 65,536
EXCERPT_CHARS = 1500
TAIL_LINES = 25
MAX_READ = 2_000_000

PASS, FAIL, WARN, ERROR, NOT_RUN = "pass", "fail", "warn", "error", "not_run"
LABEL = {PASS: "PASS", FAIL: "FAIL", WARN: "WARN", ERROR: "ERROR", NOT_RUN: "NOT RUN"}

_PATH = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./-]*$")
_RAW = re.compile(r"^:(\d{6}) (\d{6}) [0-9a-f]+ [0-9a-f]+ ([A-Z])\d*\t(.+)$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_CLOSES = re.compile(r"(?im)^\s*(?:closes|fixes|resolves)\s+#(\d+)\b")
_SUMMARY = re.compile(r"^\s*(\d+) (passing|failing)\b", re.MULTILINE)
_FAILING_LINE = re.compile(r"^\s*\d+ failing\b", re.MULTILINE)
_TITLE = re.compile(r"^\s+\d+\) (.+)$")


class VerifyError(Exception):
    """The step cannot go on. The message says why, without tokens."""


# ---------- what the pull request changes ----------

def check_scope(raw):
    """Read `git diff --raw --no-renames` of the pull request. Only small, plain, added or changed files in the
    folders the fix step may touch pass. Anything else is a problem, and the script then runs nothing from it."""
    problems, files = [], []
    for line in raw.splitlines():
        if not line.strip():
            continue
        m = _RAW.match(line)
        if not m:
            problems.append("cannot read a line of the change list")
            continue
        _old_mode, new_mode, status, path = m.groups()
        if status not in ("A", "M"):
            problems.append(f"a file was deleted or renamed ({path})")
        elif new_mode != "100644":
            problems.append(f"a file has an unexpected mode {new_mode} ({path})")
        elif not _PATH.match(path) or ".." in path.split("/"):
            problems.append("a file has an unsafe path")
        elif not path.startswith(ALLOWED_PREFIXES):
            problems.append(f"a file is outside the allowed folders ({path})")
        else:
            files.append({"status": status, "path": path})
    if not files and not problems:
        problems.append("the pull request changes nothing in app/")
    if len(files) > MAX_FILES:
        problems.append(f"too many changed files ({len(files)}, the limit is {MAX_FILES})")
    rel = [f["path"][len("app/"):] for f in files]
    return {"ok": not problems, "problems": problems, "files": files,
            "tests": [p for p in rel if f"app/{p}".startswith(TEST_PREFIX)],
            "sources": [p for p in rel if not f"app/{p}".startswith(TEST_PREFIX)]}


# ---------- reading the run folder ----------

def _text(d, name):
    try:
        with open(Path(d) / name, "rb") as f:
            return f.read(MAX_READ).decode("utf-8", "replace")
    except OSError:
        return None


def _rc(d, name):
    text = _text(d, f"{name}.rc")
    try:
        return int(text.strip()) if text is not None else None
    except ValueError:
        return None


def _json(d, name):
    text = _text(d, name)
    try:
        return json.loads(text) if text is not None else None
    except ValueError:
        return None


def mocha_summary(text):
    """(passing, failing) from mocha's summary lines, or None if the run printed no summary."""
    found = _SUMMARY.findall(text or "")
    if not found:
        return None
    return (sum(int(n) for n, kind in found if kind == "passing"),
            sum(int(n) for n, kind in found if kind == "failing"))


def failing_titles(text):
    """Titles of the tests that failed, from the numbered lines mocha prints before its summary."""
    m = _FAILING_LINE.search(text or "")
    if not m:
        return []
    out = []
    for line in text[:m.start()].splitlines():
        t = _TITLE.match(line)
        if t:
            out.append(t.group(1).strip())
    return out[:50]


def failure_excerpt(text):
    """What mocha printed about the failures: from the 'N failing' line, capped."""
    m = _FAILING_LINE.search(text or "")
    if not m:
        return ""
    return "\n".join(text[m.start():].strip().splitlines()[:TAIL_LINES])[:EXCERPT_CHARS]


def _result(status, headline, lines=(), output=()):
    return {"status": status, "headline": headline, "lines": list(lines), "output": list(output)}


def _not_run(d, what, needs_install=False):
    """The result for a check that has no result files: say why, never just 'nothing'."""
    scope = _json(d, "scope.json")
    if isinstance(scope, dict) and not scope.get("ok"):
        return _result(NOT_RUN, f"{what} was not run, because the pull request changes files outside what the fix "
                                "step may touch (see the change list below).")
    if needs_install and _rc(d, "tests-install") not in (None, 0):
        return _result(ERROR, f"{what} was not run: installing the test dependencies failed.",
                       output=[("Install log (end)", _tail(_text(d, "tests-install.log")))])
    return _result(NOT_RUN, f"{what} was not run.")


# ---------- the four checks ----------

def check_regression(d):
    after_rc, before_rc = _rc(d, "spec-after"), _rc(d, "spec-before")
    after, before = _text(d, "spec-after.txt"), _text(d, "spec-before.txt")
    if after_rc is None and before_rc is None:
        return _not_run(d, "The regression test", True)
    a, b = mocha_summary(after), mocha_summary(before)
    if a is None or after_rc is None:
        return _result(ERROR, "The regression test gave no result on the pull request's code.",
                       output=[("Output on the pull request's code", _tail(after))])
    if after_rc != 0 or a[1] or a[0] < 1:
        return _result(FAIL, "The regression test does not pass on the pull request's code.",
                       [f"On the pull request's code: {a[0]} passing, {a[1]} failing."],
                       [("Failures on the pull request's code", failure_excerpt(after))])
    if b is None or before_rc is None:
        return _result(ERROR, "The regression test gave no result on main's unfixed code (it may have crashed "
                              "before running a test), so it is not proven to catch the flaw.",
                       [f"On the pull request's code: {a[0]} passing, 0 failing."],
                       [("Output on main's unfixed code", _tail(before))])
    if before_rc == 0 and not b[1]:
        return _result(FAIL, "The regression test passes on the unfixed code too, so it does not tell the fix "
                             "from the flaw.",
                       [f"On main's unfixed code: {b[0]} passing, 0 failing.",
                        f"On the pull request's code: {a[0]} passing, 0 failing."])
    return _result(PASS, "The new test fails on the unfixed code and passes on the fix.",
                   [f"Fails on main's unfixed code: {b[1]} failing, {b[0]} passing.",
                    f"Passes on the pull request's code: {a[0]} passing, 0 failing."],
                   [("How it fails on the unfixed code", failure_excerpt(before))])


def check_suite(d):
    rc, out = _rc(d, "suite-pr"), _text(d, "suite-pr.txt")
    if rc is None:
        return _not_run(d, "The test suite", True)
    s = mocha_summary(out)
    if s is None or (rc == 0 and s[0] < 1):
        return _result(ERROR, "The test suite gave no usable result.", output=[("Output", _tail(out))])
    if rc == 0 and not s[1]:
        return _result(PASS, f"The server test suite passes on the pull request's code ({s[0]} passing, 0 failing).")
    mine = failing_titles(out)
    base_rc, base_out = _rc(d, "suite-base"), _text(d, "suite-base.txt")
    base = mocha_summary(base_out)
    excerpt = [("Failures on the pull request's code", failure_excerpt(out))]
    if base is None or base_rc is None:
        return _result(FAIL, f"The server test suite has {s[1]} failing on the pull request's code. Main's code "
                             "was not run for comparison.",
                       [f"{s[0]} passing, {s[1]} failing."] + [f"Failing: {t}" for t in mine], excerpt)
    theirs = set(failing_titles(base_out))
    new = [t for t in mine if t not in theirs]
    if new:
        return _result(FAIL, f"The pull request code has {len(new)} failing test(s) that pass on main.",
                       [f"On the pull request's code: {s[0]} passing, {s[1]} failing.",
                        f"On main's code: {base[0]} passing, {base[1]} failing."] + [f"New failure: {t}" for t in new],
                       excerpt)
    return _result(WARN, f"{s[1]} test(s) also fail on main's own code. The pull request adds no new failure.",
                   [f"On the pull request's code: {s[0]} passing, {s[1]} failing.",
                    f"On main's code: {base[0]} passing, {base[1]} failing."], excerpt)


def check_scan(d, finding):
    rc = _rc(d, "scan")
    if rc is None:
        return _not_run(d, "The re-scan")
    target = finding["file"][len("app/"):] if finding["file"].startswith("app/") else finding["file"]
    try:
        if rc != 0:
            raise sarif.SarifError("the scan step failed")
        n_results, findings = sarif.parse(sarif.load(Path(d) / "semgrep-pr.sarif"))
    except sarif.SarifError as e:
        return _result(ERROR, f"The re-scan did not finish: {e}.")
    if n_results == 0:
        return _result(ERROR, "The re-scan result is empty, which cannot be trusted (an empty scan is not a pass).")
    locations = len({(f.file, f.line) for f in findings})
    still = [f for f in findings if f.file == target and f.cwe == finding["cwe"]]
    where = f"{target}:{finding['line']} {finding['cwe']}"
    if still:
        return _result(FAIL, f"The finding ({where}) is still reported.",
                       [f"Now at line {f.line}, rules {', '.join(f.rule_ids)}." for f in still])
    return _result(PASS, f"The finding ({where}) no longer appears. The scan ran and reported "
                         f"{n_results} results at {locations} other locations.")


def check_exploit(d):
    build_rc, rc = _rc(d, "build"), _rc(d, "exploit")
    login = _json(d, "login-check.json")
    if build_rc is None and rc is None:
        return _not_run(d, "The exploit")
    if build_rc not in (None, 0):
        return _result(ERROR, "The throwaway build of the pull request failed, so the exploit was not run.",
                       output=[("Build log (end)", _tail(_text(d, "build.log")))])
    if rc is None:
        return _result(ERROR, "The exploit did not run (the throwaway container did not start or never answered).",
                       output=[("Container log (end)", _tail(_text(d, "app.log")))])
    if rc == 0:
        return _result(FAIL, "The attack succeeded against the pull request's build.",
                       ["The login SQL injection still works."])
    if rc != 1:
        return _result(ERROR, "The exploit could not give an answer"
                              + (" (the control request failed, so the target may not be the app)." if rc == 2
                                 else f" (exit code {rc})."))
    if not isinstance(login, dict):
        return _result(ERROR, "The attack failed, but the check that a real login still works did not run.")
    if not login.get("ok"):
        return _result(FAIL, "The attack failed, but a legitimate login also fails on this build.",
                       [f"Legitimate login answered HTTP {login.get('status')}."])
    return _result(PASS, "The attack failed against the pull request's build, and a legitimate login still works.",
                   ["Control request: refused as expected. Attack: no token received."])


def _tail(text):
    return "\n".join((text or "").strip().splitlines()[-TAIL_LINES:])[-EXCERPT_CHARS:]


CHECKS = (("Regression test", "regression"), ("Test suite", "suite"), ("Re-scan", "scan"), ("Exploit", "exploit"))


def evaluate(d):
    finding = _json(d, "finding.json") or {"file": "app/routes/login.ts", "line": 0, "cwe": "CWE-89"}
    return {"scope": _json(d, "scope.json"), "behind": _behind(d), "regression": check_regression(d),
            "suite": check_suite(d), "scan": check_scan(d, finding), "exploit": check_exploit(d)}


def _behind(d):
    try:
        return int((_text(d, "behind.txt") or "0").strip())
    except ValueError:
        return 0


def overall(results):
    bad = [k for _, k in CHECKS if results[k]["status"] != PASS]
    if not bad:
        return True, "All four checks passed."
    return False, f"{len(bad)} of 4 checks did not pass cleanly. Read each result below."


# ---------- the comment ----------

def render(results, pr, finding, now=None, secret=None):
    now = now or time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    ok, verdict = overall(results)
    out = [MARKER, "## Evidence from the verify step (M2-8)", ""]
    out.append(f"**{verdict}**" if ok else f"**This pull request did not verify cleanly. {verdict}**")
    out += ["", f"Pull request #{pr['number']} at commit `{pr['head_sha'][:12]}`, checked against `main` at "
                f"`{str(pr.get('base_sha', ''))[:12]}`, for issue #{finding['issue']} "
                f"({finding['file']}:{finding['line']} {finding['cwe']}). {now}.",
            "This is evidence only. The step does not merge and does not decide. It made no model call. "
            "All code from the pull request ran in throwaway containers, never in the working folder.", "",
            "| Check | Result | What it shows |", "|---|---|---|"]
    for title, key in CHECKS:
        r = results[key]
        out.append(f"| {title} | **{LABEL[r['status']]}** | {r['headline']} |")
    scope = results.get("scope")
    out += ["", "## Details", ""]
    for title, key in CHECKS:
        r = results[key]
        out += [f"### {title}: {LABEL[r['status']]}", r["headline"], ""]
        out += [f"- {line}" for line in r["lines"]]
        for label, text in r["output"]:
            if text:
                out += ["", f"<details><summary>{label}</summary>", "", "```", text.replace("```", "'''"), "```",
                        "", "</details>"]
        out.append("")
    out += ["### What the pull request changes"]
    if scope is None:
        out.append("The change list was not read.")
    elif scope["ok"]:
        out += [f"- `{f['path']}` ({'new' if f['status'] == 'A' else 'changed'})" for f in scope["files"]]
    else:
        out += [f"- Problem: {p}" for p in scope["problems"]] + [
            "- Because of this, no code from the pull request was run."]
    if results.get("behind"):
        out += ["", f"Note: the pull request is {results['behind']} commits behind `main`."]
    body = "\n".join(out) + "\n"
    if secret:
        body = body.replace(secret, "***")
    if len(body) > MAX_COMMENT_CHARS:
        body = body[:MAX_COMMENT_CHARS - 60].rstrip() + "\n\n(The rest was cut to fit GitHub's size limit.)\n"
    return body


def render_summary(results, pr, finding, repo, comment_url):
    """The short note for the ticket (spec section 4): the verdict, one line per check, and the links."""
    ok, verdict = overall(results)
    out = [SUMMARY_MARKER, "## Evidence (M2-8)", "",
           f"**{verdict}**" if ok else f"**The fix did not verify cleanly. {verdict}**", ""]
    out += [f"- {title}: **{LABEL[results[key]['status']]}**" for title, key in CHECKS]
    out += ["", f"Pull request #{pr['number']}: https://github.com/{repo}/pull/{pr['number']}",
            f"Full evidence: {comment_url}", "",
            "Evidence only. Nothing was merged or decided by this step. No model call."]
    return "\n".join(out) + "\n"


def post_comment(client, number, body, marker=MARKER):
    """One comment per marker: update ours if it exists, else create it. Returns (action, id, url)."""
    for c in client.list_issue_comments(number):
        if marker in (c.get("body") or ""):
            done = client.update_issue_comment(c["id"], body)
            return "updated", c["id"], done.get("html_url")
    done = client.create_issue_comment(number, body)
    return "created", done["id"], done.get("html_url")


# ---------- GitHub reads ----------

def pr_info(client, number, repo):
    pr = client.get_pull_request(number)
    head, base = pr.get("head") or {}, pr.get("base") or {}
    if pr.get("state") != "open":
        raise VerifyError(f"pull request #{number} is not open")
    if ((head.get("repo") or {}).get("full_name")) != repo:
        raise VerifyError(f"pull request #{number} comes from another repository. Only branches of {repo} are verified")
    if not _SHA.match(head.get("sha") or ""):
        raise VerifyError("GitHub gave no usable head commit")
    if base.get("ref") != "main":
        raise VerifyError("the pull request does not target main")
    m = _CLOSES.search(pr.get("body") or "")
    if not m:
        raise VerifyError("the pull request does not say which issue it closes (a line 'Closes #N')")
    return {"number": number, "head_sha": head["sha"], "title": pr.get("title") or "", "issue": int(m.group(1))}


def finding_from_issue(client, number):
    markers = ticket.read_markers(client.get_issue(number))
    if not markers:
        raise VerifyError(f"issue #{number} has no fingerprint line")
    path, line, cwe, _hash = markers
    return {"issue": number, "file": path, "line": line, "cwe": cwe}


# ---------- command line ----------

def _write(d, name, text):
    (Path(d) / name).write_text(text, encoding="utf-8")


def _client(env, repo, transport):
    token = (env.get(TOKEN_VARIABLE) or "").strip()
    if not token:
        raise VerifyError(f"{TOKEN_VARIABLE} is not set. Put it in .env (names are in .env.example)")
    return token, GitHubClient(token, repo, user_agent="governed-remediation-verify-step",
                               **({"transport": transport} if transport else {}))


def main(argv=None, env=None, transport=None):
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description="Evidence for the verify step.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pr-info", "scope", "report"):
        p = sub.add_parser(name)
        p.add_argument("--dir", required=True)
        if name != "scope":
            p.add_argument("--repo", required=True)
            p.add_argument("--pr", required=True, type=int)
        if name == "report":
            p.add_argument("--post", action="store_true")
    args = ap.parse_args(argv)
    token = (env.get(TOKEN_VARIABLE) or "").strip()

    def fail(message, code=1):
        print(f"verify: FAILED: {message.replace(token, '***') if token else message}", file=sys.stderr)
        return code

    try:
        if args.cmd == "pr-info":
            _, client = _client(env, args.repo, transport)
            info = pr_info(client, args.pr, args.repo)
            finding = finding_from_issue(client, info["issue"])
            _write(args.dir, "pr.json", json.dumps(info, indent=2) + "\n")
            _write(args.dir, "finding.json", json.dumps(finding, indent=2) + "\n")
            print(f"verify: pull request #{args.pr} at {info['head_sha']}, issue #{info['issue']} "
                  f"({finding['file']}:{finding['line']} {finding['cwe']})")
            return 0
        if args.cmd == "scope":
            scope = check_scope(_text(args.dir, "diff.raw") or "")
            _write(args.dir, "scope.json", json.dumps(scope, indent=2) + "\n")
            _write(args.dir, "changed-tests.txt", "".join(f"{p}\n" for p in scope["tests"]) if scope["ok"] else "")
            _write(args.dir, "changed-sources.txt", "".join(f"{p}\n" for p in scope["sources"]) if scope["ok"] else "")
            for p in scope["problems"]:
                print(f"verify: scope problem: {p}", file=sys.stderr)
            return 0 if scope["ok"] else 1
        pr = _json(args.dir, "pr.json") or {"number": args.pr, "head_sha": "unknown", "issue": 0}
        pr["base_sha"] = (_text(args.dir, "base-sha.txt") or "").strip()
        finding = _json(args.dir, "finding.json") or {"issue": pr.get("issue", 0), "file": "app/routes/login.ts",
                                                       "line": 0, "cwe": "CWE-89"}
        results = evaluate(args.dir)
        body = render(results, pr, finding, secret=token or None)
        _write(args.dir, "comment.md", body)
        ok, verdict = overall(results)
        print(f"verify: {verdict}")
        for title, key in CHECKS:
            print(f"verify:   {title}: {LABEL[results[key]['status']]}: {results[key]['headline']}")
        if args.post:
            try:
                _, client = _client(env, args.repo, transport)
                action, cid, url = post_comment(client, args.pr, body)
            except (VerifyError, GitHubError) as e:
                return fail(f"the comment was not posted ({e}). The text is saved in {args.dir}/comment.md", 3)
            print(f"verify: evidence comment {action} on pull request #{args.pr} (comment {cid})")
            summary = render_summary(results, pr, finding, args.repo,
                                     url or f"https://github.com/{args.repo}/pull/{args.pr}")
            _write(args.dir, "summary.md", summary)
            try:
                action, cid, _ = post_comment(client, finding["issue"], summary, SUMMARY_MARKER)
            except (VerifyError, GitHubError) as e:
                return fail(f"the summary on issue #{finding['issue']} was not posted ({e}). The pull request "
                            f"comment was posted. The text is saved in {args.dir}/summary.md", 3)
            print(f"verify: evidence summary {action} on issue #{finding['issue']} (comment {cid})")
        return 0 if ok else 1
    except (VerifyError, GitHubError, OSError) as e:
        return fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
