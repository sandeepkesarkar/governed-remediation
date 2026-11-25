# Governed-Remediation

I am building a demo of a governed vulnerability remediation loop, and keeping a log of it here. AI tools now find software flaws faster than teams can fix them. I want to show that the fixing side can be automated safely: scanners find flaws in a deliberately vulnerable app, an AI agent proposes fixes, other agents review them, a human approves, and a pipeline deploys. Every step is logged, cost-capped and checked by a tool. A person decides what ships.

This is a demo. It is not a client deployment and does not describe past performance.

The vulnerable app is [OWASP Juice Shop](https://github.com/juice-shop/juice-shop), v20.0.0.

## Status

| Milestone | What | State |
|---|---|---|
| M0 | Setup: repo, rules, plan, container safety baseline, public-readiness checks | Nearly done. One owner task is open: the spending limit on the model key (M0-6). |
| M1 | Local spikes: app in Docker, scanners, exploit, similarity match | Done |
| M2 | Local thin slice: one finding through the whole loop on one Mac | Mostly done. Ticket, exploit, fix (three paid OpenHands runs, $0.3453 in total), verify, and the human merge of fix pull request #13 (M2-9) are done. Next: deploy and confirm (M2-10). |
| M3 to M7 | Real parts in the loop, strengthen, AWS hosting, governance, CloudBees CI | Planned |

The task list and its status are in [`docs/PLAN.md`](docs/PLAN.md).

## Quickstart

Each step is one `make` target. Run `make help` for the full list. The common ones:

- `make build-app`, `make up`: build and start the vulnerable app on `127.0.0.1`.
- `make scan`, `make ticket`, `make exploit`: scan with Semgrep, file the issue, run the exploit against the local container.
- `make fix-dry-run`, `make fix`, `make fix-publish-saved`: the fix step. `make fix` is **paid**. Run the dry run first.
- `make verify PR=<n>`: mechanical evidence for a fix pull request, posted as one comment. No model call.
- `make test`, `make check-banned-terms`, `make scan-secrets`: the checks.
- `make down`, `make clean-all`: stop the app, remove everything labelled for this project.

Tokens and keys are named in [`.env.example`](.env.example) and explained in [`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md).

## The loop

![The loop: scan, create tickets, triage, fix, review and verify, approve and merge, deploy, confirm. The issue closes when GitHub sees a closing keyword in a merged pull request, which is a known risk and not a controlled step. Triage and the memory ledger are dashed because they are planned.](docs/images/workflow-loop.svg)

Dashed boxes are planned and not built.

## How it runs

- Everything runs in containers on one Mac: the vulnerable app, the scanners, the exploit scripts and the fixer agent. Nothing from Juice Shop is installed on the Mac.
- Every published port is bound to `127.0.0.1`. The vulnerable app is never reachable from the network.
- Every container, image, volume and network carries the label `project=governed-remediation`. One command removes them all: `make clean-all`.
- GitHub Issues are the ticket store. One ticket per file, line and vulnerability class.
- The first slice fixes one flaw: the SQL injection in the Juice Shop login. Each step is one command, started by hand.

## Planned

These are designed and not built. They are marked as planned (M4) in the diagrams.

- **Triage before the fixer.** An agent posts a verdict comment: real, likely false positive, or needs a human. Evidence checks come first. The model's own estimate follows, labelled as uncalibrated. Only a human dismisses a finding.
- **A memory ledger and cross-references.** Decisions are recorded as structured issue comments, read only from collaborators. When a new ticket matches an earlier one, a comment links the earlier repository. A developer approves the match.
- **A dependency scene.** A vulnerable package pinned in two repositories. After the first fix is merged, the second repository's ticket gets a cross-reference comment.

## Safety

- The fixer agent runs in a sandbox and sees only a throwaway copy of the app code. It gets no home folder and no cloud credentials.
- Secrets live in a local `.env` that git ignores. [`.env.example`](.env.example) lists the names only.
- Exploit scripts target only my own local containers.
- Spending on paid model calls is approved per session and capped.

## License

MIT for my own code: see [`LICENSE`](LICENSE). Juice Shop is MIT too, and its own notice stays in [`app/LICENSE`](app/LICENSE).

## Read more

- Specs: [`specs/`](specs/), starting with [`specs/M2-thin-slice.md`](specs/M2-thin-slice.md)
- Design: [`docs/HLD.md`](docs/HLD.md)
- Plan and task status: [`docs/PLAN.md`](docs/PLAN.md)
- Spike notes: [`docs/spikes/`](docs/spikes/)
- Working rules for Claude Code: [`CLAUDE.md`](CLAUDE.md)
