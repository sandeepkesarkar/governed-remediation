"""SARIF reader for the ticket step.

It turns a Semgrep SARIF file into findings: one per file, line and CWE (the fingerprint
parts, see specs/M2-thin-slice.md section 3). Two rules on one line give one finding.

It never keeps rule message text or code snippets. Only file, line, CWE, severity and rule
IDs leave this module. The repo will be public and the Semgrep Rules License does not allow
publishing rule text.

Command line (used by scripts/scan.sh):
    python -m agents.ticket_agent.sarif FILE [--expect-file F --expect-cwe C]
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# From the lowest to the highest. SARIF levels.
SEVERITY_ORDER = ("none", "note", "warning", "error")
DEFAULT_SEVERITY = "warning"  # the SARIF default when no level is given
_CWE = re.compile(r"^(CWE-\d+)\b")


class SarifError(Exception):
    """The SARIF file cannot be used. The message says why, without rule message text."""


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    cwe: str
    severity: str
    rule_ids: tuple


def _where(result):
    try:
        loc = result["locations"][0]["physicalLocation"]
        return f"{loc['artifactLocation']['uri']}:{loc['region']['startLine']}"
    except (KeyError, IndexError, TypeError):
        return "unknown location"


def _relative_path(uri, result):
    if not isinstance(uri, str) or not uri:
        raise SarifError(f"a result has no file path ({_where(result)})")
    path = uri[2:] if uri.startswith("./") else uri
    if path.startswith(("/", "app/")) or "://" in path or path.startswith(".."):
        raise SarifError(f"path '{uri}' is not relative to the app root. "
                         "Scan with the app folder as the root, so paths look like routes/login.ts")
    return path


def _location(result):
    try:
        loc = result["locations"][0]["physicalLocation"]
    except (KeyError, IndexError, TypeError):
        raise SarifError(f"result for rule '{result.get('ruleId')}' has no location") from None
    path = _relative_path(loc.get("artifactLocation", {}).get("uri"), result)
    line = loc.get("region", {}).get("startLine")
    if not isinstance(line, int):
        raise SarifError(f"result for rule '{result.get('ruleId')}' in {path} has no start line")
    return path, line


def _cwe(rule):
    for tag in rule.get("properties", {}).get("tags", []):
        m = _CWE.match(tag) if isinstance(tag, str) else None
        if m:
            return m.group(1)
    return None


def _severity(result, rule):
    level = result.get("level") or rule.get("defaultConfiguration", {}).get("level") or DEFAULT_SEVERITY
    if level not in SEVERITY_ORDER:
        raise SarifError(f"unknown severity '{level}' for rule '{result.get('ruleId')}'")
    return level


def parse(doc):
    """Return (number of results, findings). Findings are sorted by file and line."""
    if not isinstance(doc, dict) or not isinstance(doc.get("runs"), list) or not doc["runs"]:
        raise SarifError("the file is not SARIF: it has no runs")
    run = doc["runs"][0]
    if not isinstance(run, dict) or "tool" not in run:
        raise SarifError("the file is not SARIF: the first run has no tool")
    rules = {r["id"]: r for r in run["tool"].get("driver", {}).get("rules", []) if "id" in r}
    results = run.get("results", [])

    merged = {}
    for result in results:
        rule_id = result.get("ruleId")
        if not rule_id:
            raise SarifError(f"a result has no ruleId ({_where(result)})")
        if rule_id not in rules:
            raise SarifError(f"result for rule '{rule_id}' has no rule entry")
        rule = rules[rule_id]
        path, line = _location(result)
        cwe = _cwe(rule)
        if cwe is None:
            raise SarifError(f"rule '{rule_id}' has no CWE tag, so the result at {path}:{line} "
                             "has no CWE. Results without a CWE are rejected")
        severity = _severity(result, rule)
        key = (path, line, cwe)
        old = merged.get(key)
        if old is None:
            merged[key] = (severity, {rule_id})
        else:
            top = max(old[0], severity, key=SEVERITY_ORDER.index)
            merged[key] = (top, old[1] | {rule_id})

    findings = [Finding(f, ln, cwe, sev, tuple(sorted(ids)))
                for (f, ln, cwe), (sev, ids) in sorted(merged.items())]
    return len(results), findings


def read_findings(doc):
    return parse(doc)[1]


def load(path):
    path = Path(path)
    if not path.is_file():
        raise SarifError(f"no SARIF file at {path}")
    text = path.read_text()
    if not text.strip():
        raise SarifError(f"the SARIF file {path} is empty")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SarifError(f"the SARIF file {path} is not valid JSON ({e.msg} at line {e.lineno})") from None


def read_file(path):
    return read_findings(load(path))


def find_expected(findings, file, cwe):
    for f in findings:
        if f.file == file and f.cwe == cwe:
            return f
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read a Semgrep SARIF file and check it.")
    ap.add_argument("file")
    ap.add_argument("--expect-file")
    ap.add_argument("--expect-cwe")
    args = ap.parse_args(argv)
    try:
        n_results, findings = parse(load(args.file))
    except SarifError as e:
        print(f"sarif: {e}", file=sys.stderr)
        return 1
    if n_results == 0:
        print("sarif: the SARIF file has no results. An empty scan is not accepted", file=sys.stderr)
        return 1
    locations = len({(f.file, f.line) for f in findings})
    print(f"sarif: {n_results} results at {locations} locations, {len(findings)} findings")
    if args.expect_file and args.expect_cwe:
        found = find_expected(findings, args.expect_file, args.expect_cwe)
        if found is None:
            print(f"sarif: the expected finding ({args.expect_file}, {args.expect_cwe}) is missing",
                  file=sys.stderr)
            return 1
        print(f"sarif: expected finding present: {found.file}:{found.line} {found.cwe} "
              f"severity={found.severity} rules={', '.join(found.rule_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
