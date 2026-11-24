"""Step "fix", part 1: turn the ticket into the agent's task (M2-7).

It reads one issue from GitHub with the ticket token (read only use), checks that it is the finding we expect,
and writes task.json. The agent's prompt is built from the parsed fields only. It never holds the issue's own
text, so nobody can steer the agent by editing an issue.

Command line (used by scripts/fix.sh):
    python -m agents.fixer_agent.task --repo OWNER/NAME --issue 3 --expect app/routes/login.ts:CWE-89 --out out/fix/task.json
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from agents.common.github import GitHubClient, GitHubError
from agents.fixer_agent import sanity
from agents.ticket_agent.ticket import FINDING_LABEL, read_markers

TOKEN_VARIABLE = "GITHUB_TOKEN"   # the ticket token. Used here only to read one issue.
_EXPECT = re.compile(r"^(app/[A-Za-z0-9_./-]+\.[A-Za-z]+):(CWE-\d+)$")
KIND = {"CWE-89": ("sqli", "SQL injection")}


class TaskError(Exception):
    """The issue is not the finding we expected. The message says why, without tokens or issue text."""


def _slug(path, cwe):
    stem = re.sub(r"[^a-z0-9]", "", Path(path).stem.lower()) or "file"
    short, label = KIND.get(cwe, (cwe.lower().replace("-", ""), "vulnerability"))
    return stem, short, label


PROMPT = """You are fixing one security finding in a throwaway copy of the OWASP Juice Shop source. The copy is in
/workspace/app. Nothing here is a real system. Work only inside /workspace/app.

The finding: {cwe} (ticket #{issue}), in routes/{rel} at line {line}.
The code builds a SQL query by putting request input straight into the query text. Fix it so that request input can
never change the shape of the query.

Do this:
1. Read routes/{rel} and understand the query near line {line}.
2. Fix it in routes/{rel}. Use a parameterised query (replacements or bind parameters), not string building.
   Keep the change small. A valid email and password must still log in exactly as before. Keep every
   vuln-code-snippet comment in the file as it is.
3. Write a regression test at {spec}. Use mocha, chai and sinon, in the style of the specs in test/server/. Stub
   models.sequelize.query with sinon, call the login handler with a request whose email is an attack string such as
   {attack}, and check that the SQL text sent to the database does not contain that string and that the value
   goes in as a parameter instead. The test must fail on the old code and pass on your fix.
4. Run it: cd /workspace/app && npx mocha -r tsx {spec}
5. Finish with the finish tool and a two-line summary.

Rules: Change only routes/{rel} and {spec}, unless you must touch another file under routes/, lib/ or models/.
Do not run npm install or any command that needs the network. The dependencies are already installed. Do not start
the app. Do not edit package.json, config files or any other test. Do not fix any other weakness you notice.
"""


def build_task(issue, expect):
    m = _EXPECT.match(expect or "")
    if not m or ".." in expect:
        raise TaskError("--expect must look like app/routes/login.ts:CWE-89")
    want_path, want_cwe = m.groups()
    if "pull_request" in issue:
        raise TaskError("the issue is a pull request")
    if issue.get("state") != "open":
        raise TaskError("the issue is not open")
    if FINDING_LABEL not in [l.get("name") for l in issue.get("labels") or []]:
        raise TaskError(f"the issue does not carry the '{FINDING_LABEL}' label")
    found = read_markers(issue)
    if not found:
        raise TaskError("the issue has no fingerprint line")
    path, line, cwe, _ = found
    if (path, cwe) != (want_path, want_cwe):
        raise TaskError("the issue's finding does not match --expect")

    number = int(issue["number"])
    rel = path[len("app/"):]
    stem, short, label = _slug(path, cwe)
    return {
        "issue": number, "file": path, "rel_file": rel, "line": line, "cwe": cwe,
        "branch": f"fix/issue-{number}-{stem}-{short}",
        "title": f"Fix: {cwe} {stem} {label} (closes #{number})",
        "prompt": PROMPT.format(cwe=cwe, issue=number, rel=rel, line=line, spec=sanity.SPEC,
                                attack="' OR 1=1--"),
    }


def main(argv=None, env=None, transport=None):
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description="Build the fixer's task from one ticket.")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--issue", required=True, type=int)
    ap.add_argument("--expect", required=True, metavar="PATH:CWE")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    token = (env.get(TOKEN_VARIABLE) or "").strip()
    if not token:
        print(f"task: FAILED: {TOKEN_VARIABLE} is not set. Put it in .env", file=sys.stderr)
        return 1
    try:
        client = GitHubClient(token, args.repo, user_agent="governed-remediation-fix-step",
                              **({"transport": transport} if transport else {}))
        issue = client.get_issue(args.issue)
        if not isinstance(issue, dict):
            raise TaskError("GitHub gave an unexpected answer for the issue")
        task = build_task(issue, args.expect)
    except (GitHubError, TaskError) as e:
        print(f"task: FAILED: {str(e).replace(token, '***')}", file=sys.stderr)
        return 1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(task, indent=2) + "\n", encoding="utf-8")
    print(f"task: issue #{task['issue']} {task['file']}:{task['line']} {task['cwe']} -> branch {task['branch']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
