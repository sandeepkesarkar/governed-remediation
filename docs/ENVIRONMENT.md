# Environment

What the project runs on today. Recorded on 2026-11-12.

## Machine

| Item | Value |
|---|---|
| macOS | 26.6.2 (build 25G83) |
| Chip | Apple M4 (arm64) |

## Container runtime

| Item | Value |
|---|---|
| Runtime | Rancher Desktop 1.25.0 |
| Container engine mode | dockerd (shown as `moby` in Rancher Desktop settings) |
| Docker context | `rancher-desktop` |
| Docker socket | `~/.rd/docker.sock` (`DOCKER_HOST` is not set) |
| VM type | `vz`, 2 CPUs, 4 GB memory |
| Kubernetes | Enabled, version 1.37.2, API port 6443 (Traefik and Flannel on) |

Notes:

- Rancher Desktop's Kubernetes runs its own containers (Traefik, CoreDNS and others). They do not carry our project label, so `make clean-all` leaves them alone.
- Its Traefik load balancer publishes ports 80 and 443 on the Mac. Those are Rancher's, not ours. Our own services still follow the loopback rule in `docs/DOCKER-SAFETY.md`.
- The VM has 4 GB of memory. If Juice Shop, the scanners and OpenHands run at the same time, this may be tight. Check when we get there.

## Tool versions

| Tool | Version | Path |
|---|---|---|
| docker (client) | 29.9.3-rd | `~/.rd/bin/docker` |
| docker (server) | 29.9.2 | in the Rancher Desktop VM |
| docker compose | v5.7.0 | plugin |
| git | 2.50.1 (Apple Git-155) | system |
| gh | 2.92.0 (2026-04-28) | on the PATH |
| Python | 3.14.6 | `/usr/local/bin/python3` |
| make | GNU Make 3.81 | `/usr/bin/make` |

Our own Python tooling will run in a project virtual environment, not in this system Python. **Update, M2-4 onward:** tooling with a third-party dependency (pytest and friends) runs instead in the pinned `python` container (see below); no venv was needed. The exploit step (M2-6) runs the same way, in a container (see "Exploit step" below).

`scripts/check-loopback.sh` still runs directly on the Mac, and that is not the same kind of thing. It checks a fact only the host can observe: whether the app's *published host port* is actually bound to `127.0.0.1` and not reachable from the Mac's LAN address. That check has to run on the Mac. The exploit step does not need to observe anything about the host; it only needs to reach the app container, which it can do entirely inside Docker.

## Before each session

Rancher Desktop must be running, or every `docker` command fails with "failed to connect to the docker API". Start it from the terminal:

```
rdctl start
```

Wait until this prints a version:

```
docker info --format '{{.ServerVersion}}'
```

## Pinned versions

Every image, tool and library we adopt is pinned and recorded here. Add a row when you adopt one. Never use `latest`.

| Item | Kind | Pinned version | Where used | Added in |
|---|---|---|---|---|
| `bkimminich/juice-shop` | Image | `v20.0.0`, index digest `sha256:fd58bdc9745416afce8184ee0666278a436574633ea7880365153a63bfd418b0`. Native `linux/arm64` (manifest `sha256:cbdfc00de875926f20ff603fac73c5b68577e37680cf2e0c324adda42ffc1113`). | `spikes/S1/compose.yaml` | M1-1 (S1) |
| `semgrep/semgrep` | Image | `1.185.0`, index digest `sha256:67518c174185a2043fdbed16c70631b79209499b3671178e7194379b48295a0d`. Native `linux/arm64`. Engine LGPL-2.1. Rules: Semgrep Rules License v1.0 (internal use only). | `spikes/S3/compose.yaml` | M1-2 (S3) |
| `aquasec/trivy` | Image | `0.76.2`, index digest `sha256:8f6bb947dbc528902e11f2f5be52f7b519f6a39d5d148f41166f2040499768fb`. Native `linux/arm64`. Apache-2.0. | `spikes/S3/compose.yaml` | M1-2 (S3) |
| `zaproxy/zap-stable` | Image | `2.17.0`, index digest `sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af`. Native `linux/arm64`. Apache-2.0. SARIF through the Automation Framework `sarif-json` report template. | `spikes/S3/compose.yaml` | M1-2 (S3) |
| `alpine/git` | Image | `v2.54.0`, index digest `sha256:6a1fdb962814ca11508ca8d1bab94375b5b7ac4e4a9a40981c29fc32c02f095d`. Native `linux/arm64`. Used only to clone source into a volume. | `spikes/S3/compose.yaml` | M1-2 (S3) |
| `python` | Image | `3.13.18-alpine3.24`, digest `sha256:9ef1a599f863231c3d91e941389bfdc4a2d6070557243d54df1a4e57015b960e`. Standard library only. PSF licence. | `spikes/S4/Dockerfile.probe`, `spikes/S11/compose.yaml` | M1-3 (S4); row added in S11 |
| `ghcr.io/mermaid-js/mermaid-cli/mermaid-cli` | Image | `11.12.0`, index digest `sha256:bad64c9d9ad917c8dfbe9d9e9c162b96f6615ff019b37058638d16eb27ce7783`. Native `linux/arm64`, Chromium inside. MIT. Run by `make diagrams` with the project label, no published ports, and only `docs/images` mounted. | `Makefile` (`diagrams`), `docs/images/src/` | M0-10 |
| `node` (build stage of the Juice Shop Dockerfile) | Image | `24`, index digest `sha256:9d266751ca3d7fdbe651c878ffd5ad0a42fed49a18c283509267c97f025b7496`. Pinned by `make build-app` with a named build context. The Dockerfile in `app/` is unchanged. | `Makefile` (`build-app`) | M2-2 |
| `gcr.io/distroless/nodejs24-debian13` (final stage) | Image | Index digest `sha256:24bc0fe0225c7518f202a822587dad74fe143b96326b81fe5cc08c1df8bed03e` (the `latest` tag on 2026-11-18). Pinned by `make build-app` with a named build context. | `Makefile` (`build-app`) | M2-2 |
| `ghcr.io/openhands/agent-server` | Image | `1.63.1-python`, index digest `sha256:506c2e243dcc3f5092ad0909c5dff9fef621298faed9042b5d4b0375fac837a5`. Native `linux/arm64`, 5.5 GB. The OpenHands sandbox. Run with the project label, no mounts, no published ports. | `spikes/S2a/run.sh` | M1-4 (S2a) |
| `python` (slim) | Image | `3.13.18-slim`, digest `sha256:7249d5587b78209a006dc4a3b5340678f84ea729239193aa559962cd8c1fce50`. Client container for the OpenHands SDK. | `spikes/S2a/run.sh` | M1-4 (S2a) |
| `openhands-sdk`, `openhands-tools` | Python packages | `1.63.1` both (must match each other). Installed with `pip --target` inside the slim container. | `spikes/S2a/client/run.py` | M1-4 (S2a) |
| OpenHands client image (built here) | Image | `governed-remediation/fixer-client:1.63.1`, built by `make build-fixer-client` from `agents/fixer_agent/client/Dockerfile`: the pinned `python:3.13.18-slim` above plus `openhands-sdk` and `openhands-tools` `1.63.1`, with all 180 packages pinned in `agents/fixer_agent/client/requirements.lock`. Carries the project label. Holds the Anthropic key at run time, never a GitHub token. | `scripts/fix.sh` | M2-7 |
| Model for the fixer | Model | `anthropic/claude-sonnet-5-5` (Claude Sonnet 5.5), the same as spike S2a, pinned in `agents/fixer_agent/fix_run.py`. Price table: LiteLLM's, $2 per million input tokens, $10 per million output tokens. LiteLLM fetches a newer table at run time if it can, so a cost figure is only as fixed as that table. A reported cost of exactly zero stops the run's accounting loudly (`costlog.py`). | `agents/fixer_agent/fix_run.py` | M2-7 |
| Fixer caps | Setting | `max_budget_per_run` $1.00 and `max_iteration_per_run` 40 per conversation, enforced by OpenHands. Sub-agents off (`enable_sub_agents=False`, written out in `fix_run.py`). A wall-clock limit of 900 s for the whole run (`FIX_WALL_SECONDS`) and 840 s inside the client. The caps can be lowered through the environment, never raised. | `agents/fixer_agent/fix_run.py`, `scripts/fix.sh` | M2-7 |
| Model for OpenHands | Model | `claude-sonnet-5-5` (LiteLLM id `anthropic/claude-sonnet-5-5`). Spike choice, owner to confirm. | `spikes/S2a/run.sh` | M1-4 (S2a) |

## Locally built images

| Image | Built from | ID | Size | Build time | Built |
|---|---|---|---|---|---|
| `governed-remediation/juice-shop:v20.0.0-local` | `app/` (upstream commit `f356a09207c7a9550eb6fc4c3945e081922cf998`), upstream Dockerfile unchanged, by `make build-app` | `sha256:06d3684a082175490154b3a354d09ac28d450dc846abbd66c1ef7f25598e07f1` | 599,226,282 bytes (about 571 MiB), native `linux/arm64` | 5 min 18 s (second build, after the AI instruction files were removed from `app/`; the first build took 5 min 24 s) | 2026-11-18 |

The image carries the label `project=governed-remediation`. `make clean-all` removes it. The ID changes on every rebuild. The build cache and the two base images used as build contexts are not labelled objects, and `make clean-all` does not manage them.

## Secrets scan

| Item | Value |
|---|---|
| Tool | gitleaks `v8.30.1`, MIT licence (checked in the tool's own repository, `LICENSE` and the GitHub licence record). Image `ghcr.io/gitleaks/gitleaks:v8.30.1`, index digest `sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f`, native `linux/arm64`. |
| Run by | `make scan-secrets` (`scripts/scan-secrets.sh`), in a labelled container with no ports. The tracked files are streamed in as a tar, so the container sees a copy of the tracked tree and nothing else. Output is redacted. |
| Settings | `.gitleaks.toml` (default rules, and a path allowlist for the fake-key files listed in `app/PROVENANCE.md`) and `scan/secrets.conf` (the image) |
| Added in | M2-4b-prep |

## Python test tools

Our own Python code is tested in the pinned `python` image (3.13.18-alpine3.24, see above) in a labelled container, started by `make test`. The tools are installed inside that container from `requirements-dev.txt`, so nothing is installed on the Mac. Added in M2-4.

| Package | Version |
|---|---|
| pytest | 9.2.0 |
| pytest-cov | 7.1.0 |
| coverage | 7.17.3 |
| iniconfig | 2.3.1 |
| packaging | 26.3 |
| pluggy | 1.7.0 |
| Pygments | 2.21.0 |

The Semgrep image (`semgrep/semgrep:1.185.0`) is now also used by `make scan`, and the `python` image also by `make scan` and `make test`. Both are pinned in `scan/semgrep.conf`, `scan/python.conf` and the `Makefile`.

## Ticket step

`make ticket` (M2-5) runs `agents/ticket_agent/ticket.py` in the same pinned `python` image, in a labelled container with network access and no ports. It uses the Python standard library only, so **no new library or image is pinned**. It calls the GitHub REST API (`2022-11-28`) with the token in the `GITHUB_TOKEN` variable. The repo, `agents/` and `out/` are mounted read-only.

## Exploit step

`make exploit` (M2-6) runs `agents/exploit_agent/login_sqli.py` as a one-off container, in the same pinned `python` image the ticket step uses, so **no new library or image is pinned**. It uses the Python standard library only.

The container joins `exploit-net` (`compose.yaml`), a second network that `juice-shop-prod` also joins, alongside its existing `project-net`. `exploit-net` is marked `internal: true`: a container with only that network has no gateway, no DNS and no internet (proved live by `tests/network-isolation-test.sh`). `project-net` itself is unchanged from M2-3, including the loopback-published port that `make up` and `scripts/check-loopback.sh` depend on; Docker cannot publish a host port on an `internal: true` network at all, which is why `exploit-net` is a second network rather than a change to `project-net`.

The script refuses to target anything but the app's own compose service name (`juice-shop-prod`), checked before any request is sent. `agents/` is mounted read-only, `out/` read-write (this step writes its result file; the ticket step only reads).

## Tokens

| Variable | Used by | Scope | Where it goes |
|---|---|---|---|
| `GITHUB_TOKEN` | Ticket step. The fix step reads one issue with it. | Fine-grained, this repository only: Issues read and write, Metadata read. 30-day expiry (M0-9). | A one-off python container. |
| `GITHUB_FIX_TOKEN` | The publish script of the fix step only | Fine-grained, this repository only: Contents read and write, Pull requests read and write, Metadata read. 30-day expiry. Created for M2-7. | A one-off python container that runs `agents.fixer_agent.publish`. **Never** the OpenHands sandbox or the client container. `scripts/fix.sh` inspects both containers and stops if any credential variable, or the value of any token, is there. |
| `ANTHROPIC_API_KEY` | The fix client container | A key with the owner's spending limit (M0-6). | The client container. The client sends it to the sandbox inside the conversation request, so the agent can reach it in memory. See `docs/spikes/S2a-fixer-openhands.md`. |

All three live in the local `.env` (git ignores it). `.env.example` lists the names only.

### Creating `GITHUB_FIX_TOKEN`

1. GitHub, Settings, Developer settings, Personal access tokens, Fine-grained tokens, Generate new token.
2. Resource owner: your account. Repository access: **Only select repositories**, and pick only this repository.
3. Expiration: 30 days.
4. Repository permissions: Contents **Read and write**, Pull requests **Read and write**. Metadata is added as read only. Nothing else.
5. Copy the token once. Add a line `GITHUB_FIX_TOKEN=<the token>` to `.env`. Do not paste it into a chat, a terminal history or a file that is tracked.
