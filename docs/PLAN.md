# Governed-Remediation: plan

| | |
|---|---|
| Version | 0.22 |
| Date | 2026-11-25 |
| Owner | Sandeep Kesarkar |
| Design | `docs/HLD.md` |
| Working rules | `CLAUDE.md` |

This is the single plan for the project. It is meant to change. Nothing here is built yet.

## 1. How this plan works

- **Task IDs are permanent.** An ID is never reused or renumbered.
- **Statuses:** `todo`, `doing`, `done`, `blocked`, `dropped`.
- **Adding a task:** add a row with the next free ID in its milestone.
- **Removing a task:** set it to `dropped` and give the reason in the change log. Do not delete the row.
- **Rolling detail:** only the current and next milestone are broken into session-sized tasks. Later milestones stay as short lists and are broken down when they start.
- **Task size:** one task fits in one 3-hour session and has a check that proves it is done.
- **Upkeep:** update statuses at the end of every session. Re-plan once a week.
- **Timebox rule:** a spike gets one session, two at most. If it runs over, stop and re-plan.
- **Ideas that are not tasks yet** go in the parking lot (section 9).

## 2. Who does what

| Who | Does |
|---|---|
| Sandeep | Decides, approves, merges. Runs anything that creates cloud resources or costs money. |
| Claude Code (terminal) | Builds in the repo: code, tests, containers, local runs. Follows `CLAUDE.md`. |
| Claude (desktop chat) | Planning, research, and documents (HLD, this plan, spike reviews). |

Everything Claude Code needs is in the repo. Nothing depends on a chat conversation.

Time: about 3 hours a day. Prime outreach is tracked separately and is not part of these hours.

## 3. Terms

| Term | Meaning | Code kept? |
|---|---|---|
| Spike | A timeboxed experiment that answers one yes-or-no question | No. The output is a note in `docs/spikes/`. |
| Thin slice | The roughest real version of the whole loop, for one finding, with each step started by hand | Yes. It grows into the product. |
| Spec | A written description of one piece of behaviour, precise enough to build and test against | Yes |

SpecKit use: none for spikes, one light spec for the thin slice, one spec per feature after that.

## 4. Milestones

| ID | Milestone | Done when |
|---|---|---|
| M0 | Setup | Repo exists, rules and plan are committed, the clean-up command works |
| M1 | Local spikes | S1, S3, S4 and S2a each have a note with a clear result |
| M2 | Local thin slice | One finding goes through the whole loop on the Mac, in containers, with a real pull request |
| M3 | Real parts in the loop | Jenkins in Docker replaces the scripts, the fixer and reviewers run in GitHub Actions on Bedrock |
| M4 | Strengthen | Full ticket handling, dispatcher, 3 to 5 findings, failure path, evidence |
| M5 | AWS hosting | The loop runs against production on AWS, created and destroyed per session |
| M6 | Governance and demo | Caps, kill switch, metrics, control mapping, recorded demo |
| M7 | CloudBees CI | The same pipeline runs on CloudBees CI |

### Week-one goal

**Start:** 2026-11-12. **Target:** none. The 2026-11-19 date was dropped on 2026-11-17 (see the change log). **Goal:** M0, M1 and M2.

My estimate for M0 to M2 is 8 to 10 sessions. Checkpoint every five sessions: if the thin slice has not started by then, re-plan. Nothing is trimmed from the scope.

## 5. Spike register

| ID | Question | Milestone | Status |
|---|---|---|---|
| S1 | Does Juice Shop v20.0.0 run in Docker on Apple silicon, reachable only from this Mac? | M1 | done |
| S3 | Do Semgrep, Trivy and ZAP run in Docker against Juice Shop and produce SARIF? Which 3 to 5 findings do we curate? | M1 | done |
| S4 | Does a hand-written exploit for the login SQL injection succeed before a manual fix and fail after it? | M1 | done |
| S2a | Does the OpenHands SDK, headless in Docker with an Anthropic key, fix the login SQL injection in a local copy and add a test? What does it cost in tokens? | M1 | partly (mechanics answered on a toy bug) |
| S8 | Does Jenkins run in Docker from configuration as code, poll GitHub and build a pull request? | M3 | todo |
| S2b | Does the OpenHands desktop app (Agent Canvas), on a Docker backend limited to the project folder, fix the same flaw? | M3 | todo |
| S2c | Can the desktop app show a run that the headless pipeline started? | M3 | todo |
| S5 | Does OpenHands work with Claude on Bedrock, from the Mac and from GitHub Actions with short-lived credentials? | M3 | todo |
| S6 | Can the OpenHands reviewer use an OpenAI model on Bedrock? | M3 | todo |
| S7 | Can a pull request opened by a GitHub App from GitHub Actions trigger a second workflow? | M3 | todo |
| S2d | Can OpenHands itself open the pull request, in place of our script? | M3 | todo |
| S9 | Can we delegate a subdomain of `<your-domain>` from the domain registrar to AWS and get a certificate? | M5 | todo |
| S10 | Does a CDK stack bring up Fargate behind an allowlisted load balancer and destroy cleanly? | M5 | todo |
| S11 | Can a similarity match (normalized code snippet, rule or CWE filter first) link the login and search SQL injections from the S3 results, and reject unrelated findings, without a vector database? Uses Semgrep results only. No paid call. Rerun Semgrep (free) if the S3 SARIF is not on hand. Juice Shop flags both with the same rules, so this proves linking only. Similar code under a different rule needs a second codebase (parking lot). | M4 | done |

Spike order in M1: S1, S3, S4, S2a. Each later spike depends on the one before.

## 6. Tasks

### M0: Setup (about 1 session)

| ID | Task | Owner | Done when | Status |
|---|---|---|---|---|
| M0-1 | Create the private repo `governed-remediation` in the personal GitHub account. Initialize git in the local folder and push the docs. | Sandeep | The repo shows `docs/HLD.md` | done |
| M0-2 | Commit `CLAUDE.md`, this plan, the spike template, `.gitignore` and `.env.example` | Claude Code | `.env` is ignored and no secret is in the history | done |
| M0-3 | Docker safety baseline: project label on every container, image and volume, ports bound to loopback only, one clean-up command | Claude Code | The clean-up command leaves no project containers, images or volumes | done |
| M0-4 | Record tool versions (Docker, git, GitHub command line, Python) in `docs/ENVIRONMENT.md` | Claude Code | The file exists and nothing new was installed on the Mac for Juice Shop | done |
| M0-5 | Update the HLD with the planning decisions (local first, desktop app as a window, spike list) and add the local architecture drawing | Claude (chat) | HLD v0.7 is in `docs/` | done |
| M0-6 | Confirm a monthly spending limit on the Anthropic key. Put the key in the local `.env` only. | Sandeep | The limit shows in the Anthropic console | todo |
| M0-7 | Add the memory spike, the M4 memory rows, the new decisions and risks to this plan. Drop the 2026-11-19 target. | Claude (chat) | This plan is v0.3 and the change log explains each addition | done, pending merge |
| M0-8 | Docs cleanup and plan v0.4: neutral wording, new decisions and new rows (owner decision, 2026-11-18) | Claude Code | The banned-terms search on tracked files (listed in the task brief) returns nothing, and this plan is v0.4 | done, pending merge |
| M0-9 | After the cutover (M2-4b), for the new public repo: create the first GitHub token (fine-grained, this repo only, Issues read and write, Metadata read only, 30-day expiry) and put it in the local `.env` | Sandeep | `.env.example` lists the variable name. The token is first used and verified in M2-5. | done (owner, 2026-11-23). First used and verified in M2-5. |
| M0-10 | Rewrite the README for a public reader. Update the HLD diagrams and the two SVGs to the current decisions, with mermaid as the single source and a pinned mermaid container to render it (owner decision, 2026-11-18). | Claude Code | Every diagram matches the plan and spec, README links resolve, and the banned-terms search is empty | done, pending merge |
| M0-11 | Banned-terms check as a script: `scripts/check-banned-terms.sh` (`make check-banned-terms`) reads the terms from the git-ignored `.banned-terms.local`, searches tracked files and file names with `app/` excluded, and prints only file and line, never a term (owner request, 2026-11-24) | Claude Code | The check runs in a container, fails (exit 2) when there are no terms, finds a planted term, and ignores `app/`; `make test-banned-terms` passes | done, pending merge |
| M0-12 | Restore what the merge of PR #9 dropped: the `test-isolation` Makefile target and its `.PHONY` entry, the M2-7 change-log line, and an accurate M2-7 row (owner request, 2026-11-24) | Claude Code | `make test-isolation` passes, the Makefile lists the target, and this plan has the M2-7 live-run change-log line and an M2-7 row that matches what happened | done, pending merge |
| M0-13 | Resolve the merge conflict between PR #15 (M2-8) and main on `docs/PLAN.md`, by hand and locally, not in GitHub's web editor (owner request, 2026-11-25) | Claude Code | PR #15 is cleanly mergeable. The plan keeps everything from both sides: the M2-7 "done" row, the M2-8 "done, pending merge" row, the resolved parking-lot bullet and both change-log lines. | done, pending merge |

### M1: Local spikes (about 4 sessions)

| ID | Task | Owner | Done when | Status |
|---|---|---|---|---|
| M1-1 | Run spike S1 | Claude Code | Note written. The app answers on loopback and not from another device. | done |
| M1-2 | Run spike S3 | Claude Code | Note written with SARIF samples and the curated findings list | done |
| M1-3 | Run spike S4 | Claude Code | Note written. The exploit result flips after a manual fix on a scratch copy. | done |
| M1-4 | Run spike S2a | Claude Code, Sandeep approves each paid run | Note written with the diff, the test, token counts and cost | done (mechanics only, toy bug; real flaw not yet tried) |

### M2: Local thin slice (about 4 to 5 sessions)

One finding: the SQL injection in the login. Every step is one command, started by hand. Jenkins is not in this slice. A plain script does the verify step.

| ID | Task | Done when | Status |
|---|---|---|---|
| M2-1 | Write the light spec for the slice. The ticket comment format must leave room for a later verdict comment (M4-12). Spec: `specs/M2-thin-slice.md`. | The spec is reviewed and merged | done, pending merge |
| M2-2 | Vendor Juice Shop v20.0.0 under `app/` with its license and a provenance note. Build the image locally. | The image builds from `app/` | done, pending merge |
| M2-3 | Step "up": run the app container on loopback | The app answers locally | done, pending merge |
| M2-4 | Step "scan": Semgrep writes SARIF to an output folder | The login injection appears in the SARIF | done, pending merge |
| M2-4b-prep | Public-readiness: LICENSE, secrets scan, personal-detail sweep, pre-publication checks, README update (owner decision, 2026-11-18) | Claude Code | The tree is ready to copy into a public repo. The secrets scan is clean (owner decision on the 58 findings, 2026-11-18). | done (merged, PR #15) |
| M2-4b | Cutover to public (preparation by Claude Code, execution by the owner): a fresh public repo with one clean initial commit, branch protection on `main`, comments restricted to collaborators, then archive this private repo. Done before M2-5. | The public repo exists with one clean commit (true). Owner follow-ups still open: branch protection on `main`, secret scanning and push protection, archive of the old private repo. | done 2026-11-19 (cutover). Fresh single-commit public repo, history starts at `bb6d868`, MIT licence, public at https://github.com/sandeepkesarkar/governed-remediation. The old repo was renamed and is kept as a private archive. **Owner follow-ups (not new rows):** branch protection on `main`, secret scanning and push protection, and archiving the old private repo. |
| M2-5 | Step "ticket": a script creates one GitHub issue for that finding, and does not create a duplicate on a second run. The SARIF reader already exists (`agents/ticket_agent/sarif.py`, from M2-4); build the ticket step on it. | One issue exists after two runs | done 2026-11-23. Live check passed: issue #3 created by the first `make ticket`, found (nothing created) by the second; it is the only issue labelled `finding`. |
| M2-6 | Step "exploit": the hand-written exploit runs against the app | The attack succeeds before the fix | done 2026-11-23. `make exploit` exits 0 (vulnerable) on the live container, and exits 3 when refused a target other than the app's own compose service name. |
| M2-7 | Step "fix": OpenHands, headless in Docker, fixes a throwaway copy and adds a regression test. A script pushes the branch and opens a pull request linked to the issue. | A pull request exists with a fix and a test | done. Three paid runs, $0.3453 in total ($0.1417, $0.0959, $0.1076). The first two found bugs in our own setup and checks: sqlite3 not built in the sandbox and two isolation false positives (`GPG_KEY`, the client's own mounts), fixed in PR #9 and PR #11, and the second run's output was lost, which led to the rule that the sandbox output is saved before the isolation verdict. The third run produced the fix and found two publish bugs (the size cap hit unchanged files, and a `.git` folder), fixed in PR #12. PR #13 carries the fix and its regression test. It was published from that saved run with `make fix-publish-saved`, with no new paid call. It stays open and unmerged until the verify step (M2-8) has run. |
| M2-8 | Step "verify": a script builds the pull request, runs the tests, re-scans, runs the exploit against a throwaway container and posts an evidence comment | The comment shows test pass, finding gone, attack failed | done 2026-11-25, pending merge. Live run on PR #13 with the real app running: all four checks passed, the full comment is on the PR and a short linked summary on issue #3. The real app container was unchanged (same ID and start time). |
| M2-9 | Human reviews and merges on GitHub | Merged by Sandeep | todo |
| M2-10 | Steps "deploy" and "confirm": rebuild from `main`, replace the container, run the exploit and scan, close the issue | The attack fails, the finding is gone, the issue is closed | todo |
| M2-11 | Slice review: record elapsed time, token cost and human minutes. Update this plan. | Numbers are in the change log | todo |
| M2-12 | Dropped, moved to M2-4b. Was: cutover to public (owner task, after M2-11). | | dropped |

### M3: Real parts in the loop (to be broken down when M2 ends)

| ID | Item |
|---|---|
| M3-1 | Spike S8, then Jenkins in Docker replaces the verify and deploy scripts |
| M3-2 | Spikes S2b and S2c for the desktop app, one session each, off the critical path |
| M3-3 | Spikes S5, S6, S7 and S2d |
| M3-4 | The fixer as a GitHub Actions workflow on Bedrock |
| M3-5 | Two reviewer agents on pull requests |
| M3-6 | One GitHub App per agent role |

### M4: Strengthen

| ID | Item |
|---|---|
| M4-1 | Ticket agent: SARIF intake from any source, fingerprints, full label lifecycle |
| M4-2 | Dispatcher: highest severity first, three at a time |
| M4-3 | 3 to 5 curated findings, each with an exploit script and a manifest entry |
| M4-4 | Failure path: two attempts, then `needs-human` with an explanation |
| M4-5 | Path guard and CODEOWNERS |
| M4-6 | Evidence bundle and the GitHub Projects board |
| M4-7 | Memory ledger: record format for four outcomes (fixed, fix failed, false positive, upstream-pending) and the structured `/decision` issue comment. A small index fed from issue comments. Start after S11. |
| M4-8 | Cross-reference: when a new ticket matches an earlier one, post a comment that links the earlier ticket's repository (never a person). A developer approves the match with a label. A match is evidence only and never dismisses a finding by itself. |
| M4-9 | Upstream-pending: a ticket state where the finding stays open and the fixer opens no pull request. Trivy re-checks when the new base image version appears. |
| M4-10 | Update HLD section 14 (from "on paper" to a real feature) and the ticket lifecycle in section 6 |
| M4-11 | Dependency scene. Step 1: confirm Trivy finds the pinned package in a tiny repo with a lockfile. Then a second repo that pins the same `jsonwebtoken` version as Juice Shop. After the first fix is merged, the second repo's ticket gets a cross-reference comment to the first. A developer approves it with a label. |
| M4-12 | Triage agent, before the fixer. It posts a verdict comment: real, likely false positive, or needs a human, with reasons. Confidence has two parts, kept separate: evidence checks first (a pass or fail list), then the model's own estimate, labelled as uncalibrated. It works on a throwaway copy with the `vuln-code-snippet` comments stripped. The fixer's copy is unchanged. Humans make every dismissal. |

### M5: AWS hosting

| ID | Item |
|---|---|
| M5-1 | Spikes S9 and S10 |
| M5-2 | CDK base stack: registry, buckets, DNS zone, certificate, GitHub federation roles, budget alerts |
| M5-3 | CDK session stack: network, load balancer with allowlist, Fargate service, Jenkins on EC2 |
| M5-4 | Session up and down commands. Rolling deploy with rollback. |
| M5-5 | The full loop against production on AWS |

### M6: Governance and demo

| ID | Item |
|---|---|
| M6-1 | Cost caps and kill switch |
| M6-2 | Evidence bundles in S3 and the four metrics |
| M6-3 | Control mapping and the one-page threat model |
| M6-4 | Demo scenes: failure case, prompt injection attempt, kill switch, cost cap |
| M6-5 | Branch protection: GitHub Pro or a public repo (see section 7) |
| M6-6 | Demo script and recording |
| M6-7 | Dropped, moved to M2-12. Was: cutover to public (owner task). |

### M7: CloudBees CI

| ID | Item |
|---|---|
| M7-1 | Request the 7-day trial only when ready to start |
| M7-2 | Run the same pipeline on CloudBees CI and document the differences |

## 7. Decisions

### Made

| Date | Decision |
|---|---|
| 2026-11-12 | Build and prove the loop locally first. AWS hosting comes after. |
| 2026-11-12 | Locally, Juice Shop, the scanners, Jenkins and the OpenHands agent run only in containers. Nothing from Juice Shop is installed on the Mac. |
| 2026-11-12 | Thin slice before depth: one finding through the whole loop, then strengthen. |
| 2026-11-12 | First OpenHands runs use an Anthropic API key and a mid-tier Claude model. Bedrock comes in M3. |
| 2026-11-12 | OpenHands: the headless SDK is the path we build on. The desktop app is a window for the demo (fixes and past runs), always on a Docker backend. |
| 2026-11-12 | The first slice uses real GitHub pull requests with a personal access token. GitHub Apps come in M3. |
| 2026-11-12 | Git: a branch and a pull request per task. Tests first. 90% coverage on our own code. |
| 2026-11-12 | The repo is private in the personal GitHub account. |
| 2026-11-17 | DefectDojo is dropped for the demo. GitHub Issues stay the ticket store. |
| 2026-11-17 | Memory is a customer-owned ledger of decisions. Customers never see it. Outcomes recorded: fixed, fix failed, false positive, upstream-pending. |
| 2026-11-17 | People write decisions as GitHub issue comments in a structured form. No separate screen. |
| 2026-11-17 | A match to an earlier finding is based on code similarity. A developer approves it with a label. It is evidence only and never dismisses a finding automatically. |
| 2026-11-17 | The cross-reference comment on a new ticket points to the earlier repository, not to a developer. |
| 2026-11-17 | For the demo, everyone can see every repository and any developer can write or approve a decision. Roles and access checks are deferred. |
| 2026-11-17 | An upstream-pending finding stays open and the fixer opens no pull request for it. |
| 2026-11-17 | The fixer's copy keeps `data/static/codefixes/` and the `vuln-code-snippet` comments for the demo. See the risks. |
| 2026-11-17 | Planning scale for the memory design: 200 to 1,000 repositories. |
| 2026-11-17 | The 2026-11-19 target date is dropped. Work continues for about two more weeks, with a checkpoint every five sessions. |
| 2026-11-18 | License: MIT for our own code. The Juice Shop MIT notice stays under `app/`. |
| 2026-11-18 | Publish by cutover: a fresh public repo with one clean initial commit, then archive this private repo (M6-7). |
| 2026-11-18 | In the public repo, comments are restricted to collaborators. The ticket agent parses decisions only from collaborators (it checks the comment author's association). Branch protection on `main` is turned on once the repo is public. |
| 2026-11-18 | Triage: a thin triage step runs before the fixer and posts a verdict comment (real, likely false positive, or needs a human) with reasons. Confidence is shown in two separate parts: evidence checks first (pass or fail list), then the model's own estimate, labelled as uncalibrated. Humans make every dismissal. The triage agent works on a throwaway copy with the `vuln-code-snippet` comments stripped. The fixer's copy is unchanged and keeps `codefixes` and the snippets. |
| 2026-11-18 | Fix confidence follows the same two-part pattern. Parking lot; design later. |
| 2026-11-18 | Tokens: the first token is fine-grained, limited to this repo, Issues read and write and Metadata read only, 30-day expiry. A second token with Pull requests and Contents write comes at M2-7. Both live in the local `.env`. `.env.example` lists names only. |
| 2026-11-18 | Paid model calls: approved in principle, not as a standing approval. Each session still needs the owner's go-ahead, and M0-6 (spending limit) must be done first. |
| 2026-11-18 | The second-codebase spike stays parked. |
| 2026-11-18 | One ticket per location and vulnerability class. The fingerprint is file, line and CWE. Two rules on one line give one ticket. |
| 2026-11-18 | Public cutover comes right after M2 (task M2-12), in place of M6-7. |
| 2026-11-18 | Cutover before M2-5, so the ticket, the fix pull request and the evidence comment are created in the public repo. |
| 2026-11-18 | M0-9 (the first token) is created after the cutover, for the new repo. |
| 2026-11-24 | Fixer caps: $1.00 and 40 iterations per conversation, enforced by OpenHands (`max_budget_per_run`, `max_iteration_per_run`, proven live in S2a). Sub-agents stay off, written out in the code (`enable_sub_agents=False`), because a child's budget check does not come out of the parent's remaining cap. A 15-minute wall clock covers the whole run as a separate backstop. Model: `claude-sonnet-5-5`, pinned, as in S2a. |
| 2026-11-24 | Token isolation for the fixer. The agent's sandbox never holds a GitHub token. A second, separate token (`GITHUB_FIX_TOKEN`: Contents and Pull requests, write; this repository only; 30-day expiry) is used only by a plain script with no model, which turns the allowed changed files into a branch and a pull request. `scripts/fix.sh` inspects the containers and stops if any credential is present. |
| 2026-11-24 | The fixer's sandbox currently has open internet access. Accepted for now because token isolation removes the worst misuse of a write-capable credential: there is none in the sandbox, and the Anthropic key is capped by the owner's spending limit. Full network lockdown needs an egress allowlist (the model API, the package registry for the agent's installs) that we have not designed. Revisit before anything beyond this demo. See the parking lot. |
| 2026-11-24 | The fix pull request is never merged by the fix step or by Claude Code. It stays open until the verify step (M2-8) has posted its evidence, and then the owner decides. |
| 2026-11-24 | Standing rule for `scripts/fix.sh` (owner): nothing that runs after the model has been called may be able to cause the loss of the sandbox's output. The output is saved to `out/fix/tree.tar` right after the run, before the isolation verdict, on every outcome. The cleanup that runs on every way out saves it again before removing the sandbox. The watchdog never removes the sandbox. A saved tar is moved aside by the next run, never deleted. The isolation check after the run may only block publishing. `tests/isolation-test.sh` checks the order of these steps in the script. |


### Deferred

| Decision | Needed by |
|---|---|
| GitHub Pro or a public repo, for branch protection (a public repo is the chosen route, see 2026-11-18) | M6 |
| Processor type for Fargate, given images are built on Apple silicon | M5 |
| Whether to wire the pipeline so the desktop app shows real runs (only if S2c says yes) | After M3 |
| Pausing agents when the AWS session is down | After M5 |

## 8. Risks

| Risk | Response |
|---|---|
| Week one is over-committed (8 to 10 sessions for 7 available) | Checkpoint at session 5. If behind, extend the target date. Do not trim scope. |
| OpenHands is changing fast and the desktop app is early preview | Pin versions. Keep the desktop app off the critical path. Fallback is the same screen in a browser or a recording. |
| The OpenHands sandbox needs control of Docker on the Mac | Allowed for spikes. Look for a more contained mode during S2a and record the result. |
| A deliberately vulnerable app on a home network | Loopback only, containers only, removed by the clean-up command |
| Model spend during spikes | Spending limit on the key. Sandeep approves each paid run. Token counts recorded in every spike note. |
| The fixer fails on the chosen finding | Try the next curated finding. Two sessions at most before re-planning. |
| The fixer can read the answers in `data/static/codefixes/` and the `vuln-code-snippet` comments, so a result with or without memory may be inflated | Kept for the demo by decision. Say so in every result note. Compare runs on the same setup only. |
| Decision comments are untrusted text and any developer can write one | Use the structured `/decision` form, parse only that form, treat the text as data, and a human approves every match. Roles come after the demo. |
| A false positive in one repository may be a real flaw in another | A match is shown as evidence only. A developer approves it. Nothing is dismissed automatically. |
| Memory is empty on day one, so a demo needs seeded history | Label seeded records as simulated. Never describe them as past performance. |

## 9. Parking lot

- Agent Canvas automations as the engine, in place of GitHub Actions for the fixer.
- A live view of pipeline runs in the final AWS demo.
- Multi-repo operation.
- Slack or email notifications.
- Rancher Desktop's bundled Kubernetes may help the CloudBees milestone.
- Memory demo option C: a second small repository with the same flaw under a different rule, plus a base-image finding, to show the "already solved elsewhere" comment and the upstream-pending state.
- A vector index for similar code, only if S11 shows that the plain similarity match is not enough.
- Notifying a developer community or channel about a match (Slack or email).
- Access checks and roles for memory (who may see a record, who may assert a decision).
- A rule ID to CWE map, for results whose rule has no CWE tag. The slice rejects such results.
- Fix confidence in two parts (evidence checks, then an uncalibrated model estimate). Design later.
- Egress allowlist for the fixer sandbox: let it reach only the model API and the package registry, and nothing else. Needs a design (a proxy or per-host rules in Docker). Today the sandbox has open internet access (decision of 2026-11-24). Revisit before anything beyond this demo.
- Prove the regression test fails on the vulnerable code before the fix. Done in M2-8 (the verify step runs the spec on main's unfixed code and requires it to fail).
- When a closed ticket's finding returns, decide whether to reopen it or open a new one (relates to M2-8 and M4 memory). Today the ticket step reports `found #N` and does nothing else.

## 10. Change log

| Date | Change |
|---|---|
| 2026-11-12 | First draft, from the planning brainstorm |
| 2026-11-12 | Owner review: checkpoint kept, no scope trimming, extend the date if behind. M0-5 done (HLD v0.7 with the local architecture drawing). |
| 2026-11-12 | M0-1 done. Private repo `governed-remediation` created and `main` pushed. The first commit went straight to `main` because no branch existed yet. Every later task uses a branch and a pull request. The first commit also included `CLAUDE.md`, `.gitignore` and the spike template, so M0-2 is partly covered and still needs `.env.example` and a history check. |
| 2026-11-12 | M0-2 done, pending merge. Added `.env.example` and `README.md`. History scan (pattern search for Anthropic, GitHub and AWS keys and private keys, plus a filename check) found nothing. `.env` is confirmed ignored. |
| 2026-11-12 | M0-3 done, pending merge. Added `Makefile` (`make list`, `make clean-all`), base `compose.yaml` and `docs/DOCKER-SAFETY.md`. Proof run: `clean-all` removed a labelled container, network, volume and image, and left a container labelled `project=other`, an unlabelled network, volume and image, and all of Rancher Desktop's own containers and images. Rancher Desktop was started for the test; nothing was installed. |
| 2026-11-12 | M0-4 done, pending merge. Added `docs/ENVIRONMENT.md` with machine, Rancher Desktop and tool versions, the `rdctl start` step, and an empty pinned-versions table. Nothing was installed; every tool was already present. Added a parking-lot line about Rancher Desktop's Kubernetes and the CloudBees milestone. |
| 2026-11-12 | S1 and M1-1 done, pending merge. Result: yes. Juice Shop v20.0.0 runs natively on arm64 in Docker, answers on `127.0.0.1:3000` and is refused on every other address of the Mac, about 160 MiB of memory, ready in about 1 s. Note: `docs/spikes/S1-juice-shop-in-docker.md`. Added `spikes/pulled-images.txt`, and `make clean-all` now removes the listed pulled images. Pinned image added to `docs/ENVIRONMENT.md`. Carry into M2-3 (wait on an API call, not only `/`) and M2-8 (the verify container needs a different loopback port). |
| 2026-11-12 | S3 and M1-2 done, pending merge. Result: yes. Semgrep 1.185.0, Trivy 0.76.2 and ZAP 2.17.0 all run natively on arm64 in containers and produce SARIF (ZAP needs an Automation Framework plan; `zap-baseline.py` has no SARIF flag). Semgrep flags the login SQL injection at `routes/login.ts:34` with two rules. Juice Shop has no lockfile, so Trivy on the source finds no dependency vulnerabilities; dependency findings come from the image scan. Proposed curated findings: login SQLi, search SQLi, hard-coded private key, `jsonwebtoken` 0.4.0, optional ZAP CSP. Note: `docs/spikes/S3-scanners.md`. Carry-overs: M2-4 uses Semgrep only with relative paths and de-duplication by file, line and class; M4-1 reads dependency findings from the image scan and handles ZAP findings that have URLs, not lines; M4-3 picks exactly-pinned dependencies; check the Semgrep Rules License (internal use only) before M6-5 and M6-6. |
| 2026-11-12 | S4 and M1-3 done, pending merge. Result: yes. The exploit (`spikes/S4/exploit.py`) succeeded (exit 0) against both the official v20.0.0 image and an unmodified build from source at the same tag, and failed (exit 1) after a minimal manual fix in a throwaway copy, with the control request and a legitimate login still working. The fix itself was not recorded anywhere, in line with the exercise. Source build: about 6.2 minutes, 571 MiB, native arm64 -- confirms M2-2 is feasible. Peak VM memory during a build was about 2.6 GiB of the VM's 3.8 GiB; consider raising the VM's memory before M2. Note: `docs/spikes/S4-exploit.md`. Carry-over for M2-7: the fixer agent's copy of the repo must contain `app/` only, not `docs/` or `spikes/`. |
| 2026-11-17 | Plan v0.3, task M0-7. Added: spike S11 (similarity match, no paid call), M4-7 to M4-10 (memory ledger, cross-reference, upstream-pending, HLD update), nine decisions, four risks and four parking-lot items. Changed: the 2026-11-19 target is dropped and the checkpoint is now every five sessions. M0-6 (spending limit) is still open because the Anthropic key email was delayed, so S2a (M1-4) cannot start yet. No task was dropped. |
| 2026-11-17 | S11 done, pending merge. Result: partly. Semgrep 1.185.0 on Juice Shop v20.0.0 (17 results at 15 locations). The rule ID or CWE match links login:34 and search:23 and rejects every unrelated finding. A snippet score built as briefed (identifiers and literals replaced) does not separate them at any window size. A score that keeps identifiers does (Jaccard 0.257 against a highest false pair of 0.051, threshold 0.15, one positive pair), but only because both lines call `models.sequelize.query`, which is what the rule already matches. So the snippet score adds nothing beyond the rule match, and Juice Shop cannot test code similarity under a different rule. Recommend a second codebase (parking-lot item, memory demo option C) before relying on it. No paid call. Note: `docs/spikes/S11-similarity-match.md`. Carry-overs: M4-7 keys records on CWE, rule ID and location and stores no snippets (never for a secret); M4-8 filters on CWE then rule ID and uses any snippet score only to rank. No task added or dropped. This branch is stacked on the unmerged M0-7 branch (the S11 row is there). |
| 2026-11-18 | Plan v0.4, task M0-8. Docs cleanup, owner decision: neutral wording in the plan, HLD and `CLAUDE.md`, with `<your-domain>` as the domain placeholder (HLD section 11, S9). HLD v0.8: section 19 now has a pre-publication checklist (secrets scan, LICENSE file, no Semgrep rule text, no raw SARIF files) and two rows were removed. Added: decisions dated 2026-11-18 (license, cutover, collaborator-only decisions, triage, fix confidence, tokens, paid calls, second codebase parked), rows M0-8, M0-9, M4-11, M4-12, M6-7, and a parking-lot line. M2-1 now says the ticket comment format leaves room for a verdict comment. No task dropped. This branch is stacked on the unmerged S11 and M0-7 branches. |
| 2026-11-18 | Plan v0.5, task M2-1. Light spec written in `specs/M2-thin-slice.md`, done, pending merge. Added M2-12 (cutover to public, after M2-11) and two decisions (one ticket per location and class; cutover right after M2). M6-7 is dropped, moved to M2-12. Open for the owner: the fingerprint wording in HLD section 6 conflicts with the new rule, and whether verify is a paid step (the spec follows plan M2-8: no model call). |
| 2026-11-18 | M2-1 follow-up, owner decisions on PR #10. Fingerprint is file + line + CWE, with the line hash as the fallback when the line moves (not used for secrets); HLD section 6 updated and HLD is v0.9. Verify uses no model call (M2-8 stands). CWE comes from Semgrep rule tags and a result without one is rejected; a rule ID to CWE map is in the parking lot. The evidence comment is full on the pull request and a short linked summary on the ticket. The specs folder stays `specs/`. No task added or dropped. |
| 2026-11-18 | Plan v0.6, task M0-10. Added M0-10 (README for a public reader, diagrams), done, pending merge. README rewritten. The five mermaid blocks in the HLD and the two SVGs now show the triage step, the memory ledger, cross-references, upstream-pending, collaborators-only decisions, GitHub Issues as the ticket store and the file + line + CWE fingerprint, with planned (M4) items dashed and labelled. The two SVGs are rendered from `docs/images/src/*.mmd` by `make diagrams` in a pinned mermaid-cli 11.12.0 container (recorded in `docs/ENVIRONMENT.md`). HLD is v0.10. The ticket-lifecycle diagram in HLD section 6 is not changed; it waits for M4-10. |
| 2026-11-18 | Plan v0.7, task M2-2, done, pending merge. Vendored Juice Shop v20.0.0 (commit `f356a09`, checked against upstream) under `app/` without `.git` and `.github`: 1,235 files, about 48 MB, largest file about 10 MB. `app/PROVENANCE.md` records the source, the exclusions, the fake keys that a secrets scan will find (the pre-publication scan needs an allowlist for `app/`) and the licences found (MIT only; nine bundled JS files and the media carry no licence statement and none is guessed). Nine files matched an upstream ignore rule and were added with `git add -f`. Added `make build-app`: upstream's Dockerfile is unchanged and its two base images are pinned by digest through named build contexts. Cold build 5 min 24 s, 572 MiB, arm64, labelled; `make clean-all` removes it. Details in `docs/ENVIRONMENT.md`. Follow-up, owner decision: the AI-assistant instruction files that upstream ships (`AGENTS.md`, `.claude/`, `.cursor/`, `.codeium/`, `.continue/`, `.junie/`, `.ai/`, 30 files) are removed from `app/` and listed as excluded in `app/PROVENANCE.md`; a re-vendor must exclude them again. 1,205 upstream files remain. Rebuilt with `make build-app` (5 min 18 s, new image ID in `docs/ENVIRONMENT.md`). Two items added to the HLD section 19 pre-publication list: the secrets-scan allowlist for `app/`, and the decision on the nine bundled JS files with no licence statement. |
| 2026-11-18 | Plan v0.8, task M2-3, done, pending merge. Step "up": service `juice-shop-prod` in `compose.yaml` (image built by `make build-app`, port `127.0.0.1:3000`, the port S1 used, read from compose by the script), `scripts/up.sh`, and `make up`, `make down`, `make check-up`, `make test-up`. `up` waits up to 90 s for the API (`/rest/admin/application-version`, version 20.0.0), and on any failure removes the container and exits non-zero. A second run replaces the container. No Python was added; the test is a shell script (`tests/up-test.sh`, written first, 8 checks, all pass), so there is no coverage figure for it. Loopback proof: `docker port` shows `127.0.0.1:3000` only and the Mac's LAN address (en1) gives no answer. `make clean-all` left no project containers, volumes, networks or images. The spike Compose files (S1, S3, S4, S11) include `compose.yaml` and are not updated; they are throwaway. |
| 2026-11-18 | Plan v0.9, task M2-4, done, pending merge. Step "scan": `make scan` (`scripts/scan.sh`, settings in `scan/semgrep.conf`) runs the pinned Semgrep 1.185.0 with the same six rule sets as S3 and S11, `--metrics=off`, no account, on `app/` mounted read-only, and writes SARIF to `out/` (git ignores it). Paths come out relative (`routes/login.ts`). Failure cases exit non-zero with a message and leave no SARIF behind; the expected finding (default `routes/login.ts`, CWE-89) is a setting. First Python in the repo: `agents/ticket_agent/sarif.py` (one finding per file, line and CWE, CWE from the rule tags, no rule message text, results with no CWE rejected). `make test`: 42 tests, 98.8% coverage, run in the pinned Python image in a labelled container; test tools pinned in `requirements-dev.txt` and `docs/ENVIRONMENT.md`. `make test-scan` checks the scan failure cases (9 checks pass). Result: 17 results at 15 locations, the same as S11; the login finding has both rule IDs. Targets scanned were 796 here against 825 in S11, because the AI instruction files were removed from `app/` and the scan root is not a git checkout; the result counts did not change. HLD is v0.11 (repo layout lists `scan/` and `tests/`). |
| 2026-11-18 | Plan v0.10, task M2-4b-prep, done, pending merge. Added `LICENSE` (MIT, own code; `app/LICENSE` untouched). Added `make scan-secrets` with gitleaks v8.30.1 (MIT, pinned, labelled container, tracked files streamed in) and `.gitleaks.toml` with a path allowlist for the five fake-key files that `app/PROVENANCE.md` lists. **Open finding for the owner:** the scan still reports 58 findings in 20 files under `app/` (16 generic-api-key and 6 jwt file groups: test fixtures, sample users and a public blockchain address). They are not allowlisted. Nothing outside `app/` is flagged. Personal-detail sweep outside `app/`: the home-folder path in `docs/ENVIRONMENT.md` and four network addresses in `docs/spikes/S1-juice-shop-in-docker.md` replaced with placeholders. HLD section 19 now lists each pre-publication check with its status (HLD v0.12); the nine bundled JS files are kept as upstream ships them. README licence section and status table updated. Added M2-4b (cutover, before M2-5), dropped M2-12 (moved to M2-4b), and two decisions: cutover before M2-5, and M0-9 after the cutover. |
| 2026-11-18 | Plan v0.11, follow-up to M2-4b-prep (PR #15), owner decision. The 58 secrets-scan findings in `app/` (20 files: upstream tests, sample data, and two source files) are allowlisted by exact path in `.gitleaks.toml`, one entry per file, scoped to the rule IDs that fired (gitleaks `targetRules`, supported in v8.30.1), with a comment on every entry. No line fingerprints, no folder patterns, no test or sample-data folder removed (the verify step needs the tests). Every group is listed in `app/PROVENANCE.md`. `make scan-secrets` is clean. Planted-secret tests: a fake token in a file outside `app/` fails the scan, and a fake private key in an allowlisted test file also fails it (the entry is scoped to its own rule); both plants were removed. HLD is v0.13. |
| 2026-11-19 | Plan v0.12, task M2-4b, done (docs close-out). The cutover is finished: a fresh public repo with one commit (`bb6d868`, 1,263 files, MIT licence). The old private repo was renamed and is kept as a private archive. A fresh clone passes `make scan-secrets` and `make test`. M0-9 (token) stays open, now marked as an owner task for the new repo. Owner follow-ups noted on M2-4b: branch protection on `main`, secret scanning and push protection, archive of the old private repo. M2-4b-prep marked merged (PR #15). README status lines updated. No task added or dropped. |
| 2026-11-23 | Plan v0.13, task M2-5, built, live check pending the token. Added the ticket step: `agents/ticket_agent/ticket.py` (one issue per file, line and CWE; fingerprint and line hash as hidden marker lines; existing issues found by listing all issues with the `finding` label and matching the marker, so a second run creates nothing; a moved line with the same hash updates the open ticket), `agents/ticket_agent/github.py` (standard library only, token only in the header, errors scrubbed), `scripts/ticket.sh` and `make ticket`. Secret findings (rule ID contains `secrets`, or CWE-798, 259, 321, 312) store no line hash. Fixed `sarif.py`: a path may now start with `app/`; absolute paths, URLs and any `..` segment are still rejected (a mid-path `..` was missed before). Four points the spec did not settle were decided by the owner on 2026-11-23 (spec section 8). 115 tests, 99% coverage, no new library. The live run could not be done: no token in the environment or `.env`. `make scan` and the failure message were checked on the Mac. Plan header date set to today. M2-4b Done-when cell reworded to what is true. |
| 2026-11-23 | M2-5 follow-up on PR #2, owner decisions. The four defaults in spec section 8 are approved as written. The GitHub transport now refuses every redirect (urllib would forward the Authorization header to the redirect target): it raises "GitHub sent a redirect. Check the repository name", with no token in the message; tested with a fake handler call and with a real redirect from a local server on 127.0.0.1. A closed ticket whose finding returns is still reported as `found #N` and nothing else happens; the open question is a parking-lot line in section 9 of this plan (the spec has no parking lot). No task added or dropped. Plan stays v0.13. 122 tests, 99% coverage. |
| 2026-11-23 | M2-5 live check, done. Run on `main` at the PR #2 merge (`2a9ae2e`) with the owner's token (not read or printed). `make scan` found the login finding (17 results at 15 locations). No issue labelled `finding` existed. The first `make ticket` created #3 (`app/routes/login.ts:34 CWE-89`, labels `finding` and `severity:high`); the second reported `found #3`, 0 created. Exactly one finding issue exists. The body holds the fingerprint and line-hash markers, severity, CWE, the two rule IDs and a link at a commit on `main`; it holds no Semgrep message text and no source code (checked against every message and snippet in the SARIF). M2-5 and M0-9 marked done. No task added or dropped. Plan stays v0.13. |
| 2026-11-23 | Plan v0.14, task M2-6, done. Built the exploit step: `agents/exploit_agent/login_sqli.py` (control request, then the login SQL-injection bypass `' OR 1=1--`; exit 0 vulnerable, 1 not vulnerable, 2 control failed, 3 target refused), `scripts/exploit.sh` and `make exploit`. It runs as a one-off container on a second compose network, `exploit-net` (`compose.yaml`), joined only by `juice-shop-prod` and this container and marked `internal: true`: no gateway, no DNS, no internet (proved live by `tests/network-isolation-test.sh`). `project-net` from M2-3 is unchanged; Docker cannot publish a host port on an `internal: true` network, which is why isolation needed a second network rather than a change to the one `make up` already uses. The script refuses any target but the app's own compose service name (`juice-shop-prod`), checked before any request is sent. The token from a successful attack is never stored or printed, only whether one was received. Uses the same pinned `python` image the ticket step uses: no new image or library. `docs/ENVIRONMENT.md` is updated, including a note on why `scripts/check-loopback.sh` still runs directly on the Mac and is not the same kind of thing. 155 tests, 99% coverage. Live-checked on the Mac: `make up`, `make check-up` and `make test-up` all still pass (M2-3 unaffected); `make exploit` exits 0 against the running (unfixed) app with a result file holding no token; a target outside the allowlist is refused with exit 3; a throwaway container with only `exploit-net` cannot reach an external IP; `make down` and `make clean-all` remove both networks and everything else labelled. No task added or dropped. This plan version was not yet true on `main` (the branch is unmerged), so this line and the M2-6 row were corrected in place rather than stacked with a second entry. |
| 2026-11-24 | Plan v0.15, task M1-4 (spike S2a), done for mechanics, real flaw not tried. Result: partly. OpenHands agent-server `1.63.1-python` runs as a sandbox container (no mounts, no ports, labelled) driven by a pinned SDK client; Sonnet 5.5 fixed a toy bug for $0.0304 (20,026 in / 385 out tokens); the native `max_budget_per_run` and `max_iteration_per_run` work in remote mode (overshoot up to one call), so M2-7 should use them and not build a watchdog. Total spend about $0.036. Model choice (Sonnet 5.5) and starting caps ($2, 40 steps) await owner confirmation. Note in `docs/spikes/S2a-fixer-openhands.md`. ENVIRONMENT.md and `spikes/pulled-images.txt` updated. Not committed, no branch or PR, per the task. No task added or dropped. Proposed, not started: a row to restrict the sandbox's outbound network to the model API. |
| 2026-11-24 | Plan v0.16, task M2-7, built, live check pending the fix token. Added the fix step: `scripts/fix.sh` (`make fix`, `make fix-dry-run`, `make build-fixer-client`) and `agents/fixer_agent/` (`task.py` turns issue #3 into the agent's prompt from parsed fields only; `fix_run.py` drives OpenHands `1.63.1-python` in a sandbox with `max_budget_per_run` $1.00, `max_iteration_per_run` 40, sub-agents off and written out, a wall clock, then `sanity.py` runs the new regression spec and two Juice Shop specs in the sandbox; `publish.py` is a plain script that reads the sandbox's tar in memory, allows only `routes/`, `lib/`, `models/` and `test/server/` changes, and opens the branch and pull request through the GitHub API with `GITHUB_FIX_TOKEN`; `costlog.py` keeps `out/cost-log.jsonl`, prints the run and running totals and fails loudly on a cost of exactly zero). Moved the GitHub client to `agents/common/github.py` (both steps use it) and added the calls the fix step needs. `scripts/fix.sh` inspects the sandbox and client containers and stops if any credential, mount or published port is present. 279 tests, 97% coverage, no network or paid call in tests. `make fix-dry-run` passed live: no model call, baseline specs 37 passing, isolation checks passed before and after, nothing logged. Four decisions recorded in section 7 (caps and model, token isolation, open internet accepted for now, the fix pull request is never merged before verify). Two parking-lot items: an egress allowlist, and proving the regression test fails on the vulnerable code (M2-8). The spike S2a files and notes ride on this branch. Paid run not made yet: `GITHUB_FIX_TOKEN` is not in `.env`. |
| 2026-11-24 | Process deviation, M1-4 (spike S2a): the spike note and its files were meant to go out as their own pull request, but they were committed on the M2-7 branch and merged to `main` as part of PR #7, because PR #7 was merged before the split was carried out. No separate S2a pull request or branch was opened, so none needed closing. No task row changed and nothing is dropped. This is a process note only. |
| 2026-11-24 | Plan v0.17, task M0-11. Added the banned-terms script (`scripts/check-banned-terms.sh`, `make check-banned-terms`, `make test-banned-terms`, `.banned-terms.local.example`). The terms live in `.banned-terms.local`, which git ignores. The check runs in the pinned python container with no network, sees a tar copy of the tracked files outside `app/` and the terms file read-only, searches contents and file names, ignores case, and prints file, line and term number only. It exits 2 when the terms file is missing or empty, so a check with no terms cannot look clean. `tests/banned-terms-test.sh` has 12 checks and uses temporary terms files only. The real `.banned-terms.local` is still empty, so the real check has not been run against real terms. The M2-7 live run was not started. |
| 2026-11-24 | M2-7 first live run, result: no pull request, $0.1417 (220,146 tokens in, 5,744 out, 53 s, caps not hit; first line of `out/cost-log.jsonl`, running total $0.1417). The agent fixed the query with named replacements and wrote the regression spec, then told us plainly that the spec could not run in the sandbox. The cause was ours: the sandbox's npm 12 blocks install scripts, so `npm rebuild sqlite3` did nothing and still reported success, and the baseline specs never touched the database. The sanity check ran the spec, it failed to load, and no pull request was opened, which is the gate working. A second problem: the after-run isolation check stopped on `GPG_KEY`, a variable the python base image sets (Python's public release-signing key), and it had never run on the client in the dry run. Fixes (follow-up to M2-7): the script builds sqlite3 by running its own install script, and a new baseline loads the app's database layer and runs one query before any paid call; `GPG_KEY` is allowed by exact name on the client check only; the isolation check moved to `scripts/isolation.sh` with `tests/isolation-test.sh` (11 cases, including containers built to fail); the after-run isolation result is now a field in the cost log (`isolation_after`), and a failure becomes the outcome (`isolation_failed`, with the run's own outcome kept as `run_outcome`) and a non-zero exit. M2-7 stays `built, live check pending`: the paid run has to be repeated. No paid run was made for these fixes. |
| 2026-11-24 | Plan v0.18, task M0-12. The merge of PR #9 into `main` was resolved by hand and dropped the `test-isolation` Makefile target with its `.PHONY` entry and help line, and the M2-7 live-run change-log line above. Restored all three from the original commit (`37cfe65`). Also corrected the M2-7 row, which still said the live check needed `GITHUB_FIX_TOKEN` (the token has been in place since the first live run), and bumped the plan to v0.18. PR #9 itself never held a version bump or an M2-7 row change, so those were stale rather than dropped. The fixer tooling files all landed intact. No task dropped, no paid run made. M2-7 still needs its paid live run repeated. |
| 2026-11-24 | Plan v0.19, follow-up to M2-7. Second live run: $0.0959 (105,387 tokens in, 3,505 out, 48 s, caps not hit), running total $0.2376 over 2 runs. The agent's fix passed the sanity check (39 passing, including the new regression spec), but the after-run isolation check failed on the client with "has mounts" (a false positive: the client is meant to have two mounts), the script aborted before copying the output out, and the cleanup removed the sandbox, so the fix was lost and no pull request was opened. The cost log recorded `isolation_failed` with `run_outcome` ready, as built. Fixes: the client check allows exactly its two mounts by destination and mode (`/repo/agents:ro`, `/out:rw`); anything else, a wrong mode or a prefix match still fails; the output is saved before the isolation verdict on every outcome, and again in the cleanup of every exit path (standing rule in section 7); the watchdog no longer removes the sandbox; the dry run now starts the client container (no key, no model call) and runs the same save and after-run checks, which two live-run mistakes had slipped past. `tests/isolation-test.sh` now has 29 cases (client mounts, saving, and the order of steps in `fix.sh`). The M2-7 paid run still has to be repeated. No paid run was made for these fixes. |
| 2026-11-24 | Plan v0.20, follow-up to M2-7. Third live run: $0.1076 (141,819 tokens in, 4,288 out, 35 s, caps not hit), running total $0.3453 over 3 runs. The agent's fix passed the sanity check (40 passing), the output was saved to `out/fix/tree.tar` before the isolation verdict (standing rule held), and isolation passed after the run. Publishing was refused by `publish.py`, which had never seen a real sandbox tar: (1) it refused any file over 200 KB even when unchanged (a PDF test fixture, screenshots), and (2) the agent had run `git init` in its copy, leaving a `.git/` folder. Fixes: a file is exempt from the size cap only if it is byte-identical to origin/main's version at the same path (the launcher exports origin/main's `app/` with `git archive`, and `publish.py` compares byte for byte and stops if GitHub's main is no longer that commit); a new or changed file is held to 200 KB whatever its path; `.git/` is ignored, and `salvage.sh` leaves `.git` out of the saved tar. New `--publish-only` mode of `fix.sh` (`make fix-publish-saved`): before publishing a saved run it checks from that run's own recorded results (`result.json` outcome ready, sanity passed, final non-zero cost, and the cost-log entry for the same run with `isolation_after` passed; `agents/fixer_agent/saved_run.py`), then runs the full normal publish path. It makes no model call and no live isolation check. 312 tests, 97% coverage; `tests/isolation-test.sh` 32 cases. Rehearsed read-only on the real saved tar: the saved-run check passes and the plan is to commit exactly `routes/login.ts` and `test/server/loginSqlInjectionSpec.ts`. The saved run has not been published: that waits for the owner to review this change. |
| 2026-11-24 | Plan v0.21, task M2-7 done. Pull request #13 (https://github.com/sandeepkesarkar/governed-remediation/pull/13, branch `fix/issue-3-login-sqli`, "Closes #3") was opened with `make fix-publish-saved` from the third live run's saved output (`out/fix/tree.tar`, 20,224,000 bytes). It made no new paid call and no cost-log line. The saved-run check and every `publish.py` check ran first. The pull request changes two files (`app/routes/login.ts`, +1 -1, and the new `app/test/server/loginSqlInjectionSpec.ts`, +58), and its body keeps "Not yet verified" and "Do not merge". It is open and not merged: M2-8 (verify) has to run against it first, and then the owner decides. The M2-7 row now reads done. Spend for the task: three paid runs, $0.3453 in total, from `out/cost-log.jsonl`. Documentation only: no code changed. |
| 2026-11-25 | Plan v0.21, task M2-8, done, pending merge. Step "verify": `make verify PR=13` (`scripts/verify.sh`, evidence in `agents/verify_agent/`). No model call, no cost. It exports the pull request with `git archive` (never checked out) and checks the change list first: plain files only, in the folders the fix step may touch, else nothing is run. Then: (1) a throwaway image from the pull request, built with the same pins as `make build-app`; (2) a test container that installs dependencies with scripts off, builds the two native modules (sqlite3, libxmljs2) from the image's own Node headers, and is then cut off from every network; in it the new spec runs on the fix (must pass), the whole server suite runs on the fix, and the new spec runs again with the fixed files put back to main's versions (must fail), which closes the gap noted in M2-7; if the suite fails, main's code is run to separate old failures from new; (3) the same Semgrep step as `make scan` on the exported `app/`, finding must be gone; (4) the real exploit (`scripts/exploit.sh`, unchanged logic) against a throwaway container on its own `internal` network with no published port, plus a legitimate login check so a broken login cannot pass as a fixed one. Everything is labelled and removed on every exit; the real app, `project-net` and `exploit-net` are not used. One evidence comment is built for the pull request, and a second run updates it instead of adding another (tested with a fake client). **The first live post failed with HTTP 403:** a comment on a pull request needs `issues=write; pull_requests=write`, and the ticket token has Issues only. Owner decision: a new token, `GITHUB_VERIFY_TOKEN` (Issues and Pull requests write, no Contents), used for everything in this step; documented in `.env.example` and `docs/ENVIRONMENT.md`. Owner also asked for the spec's short summary on the ticket: it is a separate comment on issue #3 (own hidden marker, updated on a re-run) that links the pull request and its full comment. `scan.sh` and `exploit.sh` gained optional environment overrides, defaults unchanged. Live runs: four dry runs fixed three of our own mistakes (frontend files excluded from the test copy; libxmljs2 needs building; node-gyp needs the local headers because the container has no capabilities), then clean runs; the last one ran with the real app up (`make up`), posted both comments (PR comment 7168888593, issue comment 7168889394) and left the real container untouched. Result on PR #13: regression spec fails before (2 failing) and passes after (3 passing); suite 255 passing; finding gone from 15 results at 14 other locations; attack failed (control 401, attack 401) and a legitimate login works. Build cache from the image build stays in Docker (not labelled; `docker builder prune` clears it). 379 tests, 97% coverage. |
| 2026-11-25 | Plan v0.22, task M0-13. PR #15 (M2-8) was opened from a branch that predated the merge of PR #14 (M2-7 done), so both changed the plan's date line, the M2-7 and M2-8 rows and the end of the change log. Resolved locally with `git merge origin/main` (no rebase, no force-push), by hand, keeping both sides: date 2026-11-25; the M2-7 row as on `main` (done, three runs); the M2-8 row from this branch (done, pending merge); the parking-lot bullet "Done in M2-8"; both change-log lines in order (M2-7 done, then M2-8 done). Both lines say "v0.21" because each was written on its own branch; the version is now v0.22. Nothing else in the pull request was touched. |
