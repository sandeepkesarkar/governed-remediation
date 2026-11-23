"""Step "ticket": one GitHub issue per file, line and CWE (specs/M2-thin-slice.md sections 3 and 4).

It reads the SARIF reader's findings and, for each one, finds the existing issue by its
fingerprint or creates one. A second run creates nothing.

The body is written from fields only: severity, CWE, rule IDs, a link, the fingerprint and a
short line hash. It never holds rule message text or code. For a secret finding it holds no line
hash either, so nothing about the secret is stored. The token comes from the environment.

Command line (used by scripts/ticket.sh):
    python -m agents.ticket_agent.ticket SARIF --commit SHA [--repo OWNER/NAME] [--only FILE:CWE]
"""
import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from agents.ticket_agent import sarif
from agents.ticket_agent.github import GitHubClient, GitHubError

TOKEN_VARIABLE = "GITHUB_TOKEN"   # the name in .env.example
FINDING_LABEL = "finding"
SECRET_CWES = {"CWE-798", "CWE-259", "CWE-321", "CWE-312"}
SEVERITY = {"error": "high", "warning": "medium", "note": "low", "none": "low"}
LABEL_COLORS = {"finding": "5319e7", "severity:high": "b60205", "severity:medium": "fbca04",
                "severity:low": "0e8a16"}
HASH_LENGTH = 16

_FINGERPRINT = re.compile(r"<!-- gr:fingerprint (.+):(\d+):(CWE-\d+) -->")
_LINEHASH = re.compile(r"<!-- gr:linehash ([0-9a-f]{%d}) -->" % HASH_LENGTH)
_LOCATION = re.compile(r"^- Location: .*$", re.MULTILINE)
_SHA = re.compile(r"^[0-9a-f]{40}$")


class TicketError(Exception):
    """The step cannot go on. The message says why, without tokens, rule text or code."""


@dataclass
class Outcome:
    created: int = 0
    found: int = 0
    moved: int = 0
    lines: list = field(default_factory=list)


def fingerprint(path, line, cwe):
    return f"{path}:{line}:{cwe}"


def line_hash(text):
    """A short hash of the line with all whitespace removed. It cannot be read back into code."""
    stripped = re.sub(r"\s+", "", text)
    return hashlib.sha256(stripped.encode()).hexdigest()[:HASH_LENGTH]


def severity_label(level):
    return f"severity:{SEVERITY[level]}"


def is_secret(finding):
    """A secrets rule, by rule ID or by CWE. Such a finding gets no line hash."""
    return finding.cwe in SECRET_CWES or any("secrets" in r.lower() for r in finding.rule_ids)


def _location_line(repo, commit, path, line):
    return f"- Location: [{path}:{line}](https://github.com/{repo}/blob/{commit}/{path}#L{line})"


def build_title(finding, path):
    return f"[{SEVERITY[finding.severity]}] {finding.cwe} in {path}"


def build_body(finding, path, repo, commit, hash_):
    rules = ", ".join(f"`{r}`" for r in finding.rule_ids)
    markers = [f"<!-- gr:fingerprint {fingerprint(path, finding.line, finding.cwe)} -->"]
    if hash_:
        markers.append(f"<!-- gr:linehash {hash_} -->")
    return "\n".join(markers + [
        "",
        f"- Severity: {SEVERITY[finding.severity]}",
        f"- CWE: {finding.cwe}",
        f"- Rules: {rules}",
        _location_line(repo, commit, path, finding.line),
        "",
        "## Verdict (M4-12)",
        "",
        "## Evidence (M2-8)",
        "",
    ])


def _markers(issue):
    body = issue.get("body") or ""
    m = _FINGERPRINT.search(body)
    if not m:
        return None
    h = _LINEHASH.search(body)
    return m.group(1), int(m.group(2)), m.group(3), (h.group(1) if h else None)


def make_line_reader(app_dir):
    """Return read_line(path, line) that reads one source line from the app folder."""
    root = Path(app_dir).resolve()

    def read_line(path, line):
        err = TicketError(f"cannot read the source line for {path}:{line}")
        target = (root / path).resolve()
        if root not in target.parents or line < 1:
            raise err
        try:
            lines = target.read_text(errors="replace").splitlines()
        except OSError:
            raise err from None
        if line > len(lines):
            raise err
        return lines[line - 1]
    return read_line


def select(findings, only):
    """Keep the findings named by FILE:CWE entries (file as the SARIF gives it). No entries keeps all."""
    if not only:
        return findings
    wanted = set()
    for entry in only:
        file, _, cwe = entry.rpartition(":")
        if not file or not re.fullmatch(r"CWE-\d+", cwe):
            raise TicketError(f"--only must look like FILE:CWE, for example routes/login.ts:CWE-89 (got '{entry}')")
        wanted.add((file, cwe))
    kept = [f for f in findings if (f.file, f.cwe) in wanted]
    if not kept:
        raise TicketError("no finding matches --only. Nothing was created")
    return kept


def process(findings, client, *, repo, commit, prefix, read_line):
    """Create or find one issue per finding. Everything that can fail without a write happens first."""
    plan = []
    for f in findings:
        path = prefix + f.file
        secret = is_secret(f)
        plan.append((f, path, None if secret else line_hash(read_line(f.file, f.line))))

    issues = [i for i in client.list_issues(FINDING_LABEL) if "pull_request" not in i]
    known = [(i, m) for i in issues if (m := _markers(i))]
    by_fingerprint = {fingerprint(m[0], m[1], m[2]): i for i, m in known}

    out = Outcome()
    claimed = set()
    rest = []
    for item in plan:          # pass 1: exact matches claim their tickets first
        f, path, _ = item
        issue = by_fingerprint.get(fingerprint(path, f.line, f.cwe))
        if issue:
            claimed.add(issue["number"])
            out.found += 1
            out.lines.append(f"found #{issue['number']} {path}:{f.line} {f.cwe}")
        else:
            rest.append(item)

    for f, path, hash_ in rest:  # pass 2: a moved line, or a new ticket
        moved = None
        if hash_:
            for issue, (m_path, m_line, m_cwe, m_hash) in known:
                if (issue["number"] not in claimed and issue.get("state") == "open"
                        and m_path == path and m_cwe == f.cwe and m_hash == hash_):
                    moved = (issue, m_line)
                    break
        if moved:
            issue, old_line = moved
            claimed.add(issue["number"])
            body = issue["body"].replace(fingerprint(path, old_line, f.cwe), fingerprint(path, f.line, f.cwe), 1)
            body = _LOCATION.sub(lambda _: _location_line(repo, commit, path, f.line), body, count=1)
            client.update_issue(issue["number"], body)
            out.moved += 1
            out.lines.append(f"moved #{issue['number']} {path}: line {old_line} to {f.line} {f.cwe}")
            continue
        labels = [FINDING_LABEL, severity_label(f.severity)]
        for name in labels:
            client.ensure_label(name, LABEL_COLORS[name])
        created = client.create_issue(build_title(f, path), build_body(f, path, repo, commit, hash_), labels)
        out.created += 1
        out.lines.append(f"created #{created['number']} {path}:{f.line} {f.cwe}")
    return out


def _fail(message):
    print(f"ticket: FAILED: {message}", file=sys.stderr)
    return 1


def main(argv=None, env=None, transport=None):
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description="Create one GitHub issue per finding, without duplicates.")
    ap.add_argument("sarif")
    ap.add_argument("--repo", help="owner/name. Default: the GITHUB_REPOSITORY variable")
    ap.add_argument("--commit", help="the full 40-character commit SHA the links point to")
    ap.add_argument("--app-dir", default="app", help="the app folder, to read source lines for the line hash")
    ap.add_argument("--prefix", default="app/", help="added to SARIF paths to make repo-root paths")
    ap.add_argument("--only", action="append", default=[], metavar="FILE:CWE",
                    help="only this finding (repeatable). File as the SARIF gives it")
    args = ap.parse_args(argv)

    token = (env.get(TOKEN_VARIABLE) or "").strip()
    if not token:
        return _fail(f"{TOKEN_VARIABLE} is not set. Put it in .env (names are in .env.example) "
                     "and run the step with make ticket")
    repo = args.repo if args.repo is not None else env.get("GITHUB_REPOSITORY", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        return _fail("the repository must look like owner/name (use --repo or GITHUB_REPOSITORY)")
    if not args.commit or not _SHA.match(args.commit):
        return _fail("--commit is required: the full 40-character commit SHA, in lower case")

    try:
        _, findings = sarif.parse(sarif.load(args.sarif))
        if not findings:
            raise TicketError("the SARIF file has no findings. An empty scan is not accepted")
        findings = select(findings, args.only)
        client = GitHubClient(token, repo, **({"transport": transport} if transport else {}))
        out = process(findings, client, repo=repo, commit=args.commit, prefix=args.prefix,
                      read_line=make_line_reader(args.app_dir))
    except (sarif.SarifError, TicketError, GitHubError) as e:
        return _fail(str(e).replace(token, "***"))
    for line in out.lines:
        print(f"ticket: {line}")
    print(f"ticket: {out.created} created, {out.found} found, {out.moved} moved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
