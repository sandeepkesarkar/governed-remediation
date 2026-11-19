# Working rules for Claude Code

Governed-Remediation is a demo of a governed vulnerability remediation loop: scanners find flaws in a deliberately vulnerable app, an AI agent (OpenHands) fixes them, other agents review, a human approves, and a pipeline deploys.

Read these before doing anything:

1. `docs/HLD.md` for the design.
2. `docs/PLAN.md` for what to do next. Work only on tasks listed there.

If a rule here conflicts with a request, stop and ask the owner.

## What you may do

- Write code, tests, container definitions and documentation in this repo.
- Run containers and tests locally.
- Create branches, commits and pull requests.

## What you must not do without the owner's go-ahead in the same session

- Anything that creates cloud resources or costs money. This includes AWS deploys and any run that calls a paid model API.
- Merging a pull request. The owner merges.
- Installing software on the Mac.
- Starting a task that is not in `docs/PLAN.md`. Propose it as a new row first.

## Safety rules

- **Containers only.** Juice Shop, the scanners, Jenkins and the OpenHands agent run only in containers. Never install or run Juice Shop or its dependencies directly on the Mac.
- **Loopback only.** Bind every published port to `127.0.0.1`. The vulnerable app must never be reachable from the network.
- **Label everything.** Every container, image, volume and network carries the label `project=governed-remediation`.
- **One clean-up command** removes everything with that label. Keep it working.
- **OpenHands sandbox.** Never use the unsandboxed local runtime. The agent's container may see a throwaway copy of the repo and nothing else from the Mac. No home folder mounts. No AWS credentials.
- **Exploit scripts** may target only our own local containers, and later our own AWS environment. Never any other host.
- **Our own Python tooling** may run in a project virtual environment. Everything else runs in containers.

## The app is the patient

- `app/` holds the vendored Juice Shop source. Do not fix its vulnerabilities yourself. Fixing them is the job of the fixer agent, and that is what the demo shows.
- Change `app/` by hand only to vendor or update it, and say so in the pull request.

## Secrets

- No secrets in the repo, ever. Keys live in a local `.env` that git ignores. Keep `.env.example` current, with names only.
- Never print a secret to the terminal, a log or a pull request.

## Git

- One branch and one pull request per task. Branch name: `task/<task-id>-<short-name>`.
- Put the task ID in the commit message and the pull request title.
- Small commits. Never push to `main`. Never force-push.

## Tests

- Write tests first for our own code.
- Coverage on our own code is at least 90%. `app/` and `spikes/` are excluded.
- A task is done only when its "done when" check in the plan passes.

## Spikes and specs

- Spike code goes in `spikes/<spike-id>/` and is thrown away. It needs no tests.
- Every spike ends with a note in `docs/spikes/`, written from `docs/spikes/TEMPLATE.md`.
- A spike gets one session, two at most. If it runs over, stop and report.
- The thin slice gets one light spec. After that, one spec per feature.

## Versions

- Pin every image, tool and library to a version. Record them in `docs/ENVIRONMENT.md`.

## Documents

- This is a demo. Never describe it as a client deployment or as past performance.
- Plain language, short sentences.

## End of every session

- Update task statuses in `docs/PLAN.md`.
- Add a line to the plan's change log for anything added, dropped or re-estimated.
- Never delete a task row. Mark it `dropped` with a reason.

## When unsure

Stop and ask. A wrong guess costs more than a question.
