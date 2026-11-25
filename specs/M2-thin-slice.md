# Spec: the thin slice (M2)

| | |
|---|---|
| Task | M2-1 |
| Date | 2026-11-18 |
| Status | Decisions recorded 2026-11-18 |
| Design | `docs/HLD.md` sections 6, 8 and 9 |
| Plan | `docs/PLAN.md`, tasks M2-2 to M2-11, and the cutover M2-4b |

## 1. Scope

One finding goes through the whole loop on the Mac, in containers: the SQL injection in the login of Juice Shop v20.0.0 (`routes/login.ts:34`, CWE-89). Each step is one command, started by hand. A plain script does the verify step. Jenkins is not in this slice.

**Non-goals:** triage (M4-12), memory (M4-7 to M4-9), more than one finding, the dispatcher, AWS.

## 2. Steps

Each step is a command. A failed step stops the run and prints why. Nothing later runs on a failed step.

| # | Step (task) | Input | Output | Failure case |
|---|---|---|---|---|
| 1 | **up** (M2-3) | The image built from `app/` | A container on `127.0.0.1` only, labelled `project=governed-remediation` | The health call (an API path, not only `/`) does not answer in time. Remove the container, exit non-zero. |
| 2 | **scan** (M2-4) | The `app/` source, Semgrep pinned | A SARIF file in an output folder, ignored by git | Semgrep crashes, or the login finding is missing. Exit non-zero. Never carry on with an empty result. |
| 3 | **ticket** (M2-5) | The SARIF file | One GitHub issue, or the existing issue found by fingerprint | GitHub refuses (token or rate limit). Create nothing, exit non-zero. A half-created issue is never left behind without its fingerprint. |
| 4 | **exploit** (M2-6) | The running app | Exit 0 if the attack works (before the fix). The result is saved. | The control request fails, so the target is not the app we think. Exit with a distinct code. |
| 5 | **fix** (M2-7) | The finding and a throwaway copy of `app/` only | A branch with a fix and a regression test, and a pull request linked to the issue | The agent fails, or the tests fail. No pull request. A comment on the ticket says so. |
| 6 | **verify** (M2-8) | The pull request branch | An evidence comment: tests pass, finding gone, attack fails | Any proof fails. The comment says which, and the pull request stays unmergeable by the human's choice. |
| 7 | **human merge** (M2-9) | The pull request and the evidence comment | A merge to `main` by the owner | None. The owner can close the pull request instead. |
| 8 | **deploy** (M2-10) | `main` | The container rebuilt and replaced | The health check fails. Keep the previous container. |
| 9 | **confirm** (M2-10) | The new container | Exploit fails, scan clean, issue closed | The attack still works or the finding is still there. The issue stays open. |

Safety rules apply to every step: containers only, loopback only, the fixer's copy holds `app/` and nothing else, no host credentials in any container.

## 3. Ticket rule

**Decided 2026-11-18:** one ticket per location and vulnerability class. The two Semgrep rules on the login line become one ticket.

**Fingerprint:** file, line and CWE. Example: `routes/login.ts` + `34` + `CWE-89`. Paths are relative to the repo root. The fingerprint is written into the ticket body in a fixed, machine-readable line, and is also what the ticket step searches for. A second run finds the ticket and creates nothing. It may update the rule list.

**If line numbers move.** The ticket also stores a short hash of the flagged line, with whitespace stripped. The hash is not code. It cannot be read back into code. The lookup works in this order:

1. Exact match on file, line and CWE. Use that ticket.
2. No exact match: look for an open ticket with the same file and CWE whose line hash matches. That is the same finding, moved. Use that ticket and update the line.
3. Neither: create a new ticket.

The line hash is not used for secret findings, so no hash of a secret is stored. A secret finding that moves gets a new ticket. The HLD and this spec now agree (section 7, decision 1).

## 4. Ticket body

The body is written from fields, never from scanner message text. This repo will go public, and the Semgrep Rules License does not allow publishing rule text.

- Title: `[<severity>] <vulnerability class> in <file>`
- Severity (from the SARIF level) and CWE
- Rule IDs only, as a list. No rule message text.
- A link to `file:line` at the pinned commit
- The fingerprint line and the line hash
- Labels: `finding` and the severity label (HLD section 6)
- Two empty, labelled sections, kept in this order:
  - `## Verdict (M4-12)`. Left empty in the slice. The later triage agent writes its verdict comment under this heading.
  - `## Evidence (M2-8)`. The verify step posts a short summary here that links to the full evidence comment on the pull request.

Comments written by our scripts start with a hidden marker line (`<!-- gr:verdict -->`, `<!-- gr:evidence -->`) so a later run can find and update its own comment instead of adding another.

## 5. Keys and paid calls

| Step | Needs |
|---|---|
| up, scan, exploit | Nothing. No key, no cost. |
| ticket | `GITHUB_TOKEN`: Issues read and write, Metadata read (M0-9). |
| fix | The Anthropic key. **Paid.** `GITHUB_FIX_TOKEN` to open the pull request: Contents and Pull requests write, this repo only. |
| verify | `GITHUB_VERIFY_TOKEN`: Issues and Pull requests write, no Contents. It posts the evidence comment on the pull request and a short summary on the issue. Uses no model (section 7, decision 2). |
| deploy, confirm | Not built yet. Their needs are set when M2-10 starts. |

Three GitHub tokens, each with one job. `docs/ENVIRONMENT.md` has the table and how each is made.

Paid calls need the owner's go-ahead in that session, and the spending limit (M0-6) must be done first.

## 6. Test plan

Tests come first. Our own code needs at least 90% coverage. `app/` and `spikes/` are excluded.

- **SARIF reader:** unit tests on small hand-made SARIF files. Two rules on one line give one finding. A result with no CWE is rejected with a clear error.
- **Fingerprint:** same input gives the same fingerprint. A moved line with the same hash is found. A different line with a different hash is new. A moved secret finding is not matched by hash and gets a new ticket.
- **Ticket body:** contains severity, CWE, rule IDs and the link. A test fails if the body contains the rule message text from the sample SARIF. Both labelled sections are present.
- **Ticket step:** runs against a **fake GitHub client**. A second run creates no duplicate. A GitHub error creates nothing.
- **Step runner:** each step's failure case stops the run with a non-zero exit.
- **Not unit tested:** the container steps (up, exploit, deploy). Their check is the "done when" in the plan, run on the Mac.
- **First real run:** needs the token from M0-9, and is the proof for M2-5.

## 7. Decisions (owner, 2026-11-18)

1. **Fingerprint:** file + line + CWE, with the whitespace-stripped line hash as the fallback when the line moves. Rule IDs are listed in the ticket but are not part of the key. The line hash is not used for secret findings. HLD section 6 now says the same.
2. **Verify uses no model call.** Plan M2-8 is correct. Only the fix step is paid.
3. **CWE comes from Semgrep rule tags.** A result with no CWE is rejected in the slice. A rule ID to CWE map is in the parking lot.
4. **Evidence comment:** the full comment goes on the pull request. The ticket gets a short summary under the Evidence heading that links to it.
5. **The specs folder stays `specs/`.**

## 8. Decisions for the ticket step (owner, 2026-11-23)

The spec was silent on these four points. The owner chose the defaults below when M2-5 was built.

1. **Paths.** The scan gives paths relative to the app root (`routes/login.ts`). The ticket step adds `app/`, so the fingerprint, the title and the link use repo-root paths: `app/routes/login.ts` + `34` + `CWE-89`. The `--only` filter uses the scan's path.
2. **Link commit.** Links point to the full SHA of the git `HEAD` of the checkout at run time.
3. **Secret findings.** A finding is a secret finding if any of its rule IDs contains `secrets`, or its CWE is 798, 259, 321 or 312. It gets no line hash, and its source line is not read.
4. **Repo, token, labels.** The repo comes from the `origin` remote (or `GITHUB_REPOSITORY`). The token is `GITHUB_TOKEN`. Labels are `finding` and `severity:high`, `severity:medium` or `severity:low` (SARIF error, warning, note or none). A missing label is created when the first ticket is.

Also: existing tickets are found by listing all issues with the `finding` label and reading the fingerprint marker, not by the search API, because the search index lags and could let a duplicate through. `make ticket` creates only the slice's finding (`SCAN_EXPECT_FILE` and `SCAN_EXPECT_CWE`), not all 15 locations.
