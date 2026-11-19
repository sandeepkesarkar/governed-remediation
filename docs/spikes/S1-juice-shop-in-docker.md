# Spike S1: Juice Shop in Docker

| | |
|---|---|
| Date | 2026-11-12 |
| Time spent | One session, inside the timebox |
| Result | Yes |

## Question

Does Juice Shop v20.0.0 run in Docker on Apple silicon, reachable only from this Mac?

## What we did

- Checked the image manifest with `docker buildx imagetools inspect bkimminich/juice-shop:v20.0.0`.
- Wrote `spikes/S1/compose.yaml`. It includes the base `compose.yaml` and adds one service with the project label, the `project-net` network and the port `127.0.0.1:3000:3000`.
- Pulled the image with `--platform linux/arm64`, started it with `docker compose up -d`, and called the home page and APIs with `curl`.
- Tried to reach port 3000 on every address the Mac has.
- Added `spikes/pulled-images.txt` and extended `make clean-all` to remove the listed images by name. Ran it.
- Environment: Rancher Desktop 1.25.0, dockerd mode, Docker 29.9.2, Compose v5.7.0, macOS 26.6.2 on an M4.

## What happened

**Image.** `bkimminich/juice-shop:v20.0.0` is a multi-arch image with native `linux/amd64` and `linux/arm64` builds. It runs natively. There is no emulation.

| Item | Value |
|---|---|
| Image index digest (pinned in Compose) | `sha256:fd58bdc9745416afce8184ee0666278a436574633ea7880365153a63bfd418b0` |
| arm64 manifest digest (the one that ran) | `sha256:cbdfc00de875926f20ff603fac73c5b68577e37680cf2e0c324adda42ffc1113` |
| Image architecture | `arm64`, `linux` |
| Size on disk | 576 MB |
| App version reported | `{"version":"20.0.0"}` |

The image has no shell and no `node` binary, so we could not ask the process for its architecture. The evidence is the manifest we pulled and the image's own `Architecture` field.

**The app works.**

- `GET /` returned `200` with the title "OWASP Juice Shop".
- `POST /rest/user/login` with a wrong password returned `401` "Invalid email or password." The login API is answering.
- `GET /rest/products/search?q=apple` returned `200` with JSON.

**Loopback only.** The Mac's only listener on port 3000 was `127.0.0.1:3000` (owned by `limactl`, Rancher Desktop's VM tool). Results:

| Address | Result |
|---|---|
| `127.0.0.1` | `200` |
| `<lan-address>` (Wi-Fi or Ethernet address of the Mac) | connection refused |
| `<vm-bridge-address>` (the Rancher Desktop VM bridge) | connection refused |
| Two `<link-local-address>` values (169.254.x.x) | connection refused |
| `::1` (IPv6 loopback) | connection refused |
| Two global IPv6 addresses of the Mac | connection refused |

Rancher Desktop's port forwarding honours the `127.0.0.1` bind. It does not widen it to the network.

A test through the Mac's own `.local` name returned `200`, but it resolved to `127.0.0.1`. The Mac maps its own name to loopback, so that result is not a network test and we did not count it. The macOS firewall is off, so the refusal comes from the bind address and not from the firewall.

To test from a phone on the same network, open `http://<lan-address>:3000/`. It should fail to connect.

**Start-up and memory.**

| Measure | Value |
|---|---|
| Image pull (first time, 576 MB) | 10.3 s |
| `compose up` until the container is started | 0.5 s |
| Start to first `200` on `/` | 1.1 s |
| Memory, idle | 159.5 MiB |
| Memory, after 60 search requests | 165.1 MiB |
| CPU, idle | about 0.9% |
| Rancher VM memory (whole VM) | 3.8 GiB, 2 CPUs |

One Juice Shop container uses about 4% of the VM's memory.

**Clean-up.** `make clean-all` removed the container, the network and the pulled image. Afterwards there were no labelled containers, networks, volumes or images, no `bkimminich/juice-shop` image, and nothing listening on port 3000. The Docker event log showed only the spike's own container and network being destroyed. The 9 other images were still there.

## Cost

None. No paid call was made.

## Decision

Go. Juice Shop v20.0.0 runs natively in Docker on this Mac and is reachable only from loopback. Use the pinned image in M2-2 as the base for the vendored build, and keep the loopback port form from `spikes/S1/compose.yaml`.

## Surprises and risks

- **Pulled images need their own clean-up.** They carry no project label. `spikes/pulled-images.txt` and the extended `clean-all` now handle this. Rule for every task: add an image to that list before pulling it. This changes `docs/DOCKER-SAFETY.md` (updated) and is relevant to M0-3 and every later task that pulls an image.
- **The image is minimal.** It has no shell, no `node` and no `uname`. Debugging inside it needs another container sharing its network or process space. It will matter in M2-2 if we build from `app/`.
- **The startup is fast.** The home page answered about 1 second after start. The app may still be loading its challenge data after that, so M2-3 should wait on an API call, not only on `/`.
- **Port 3000 is a fixed host port.** A second copy of the app (for the throwaway verify container in M2-8) needs a different loopback port.
- **VM size.** The Rancher VM has 4 GB. One Juice Shop is small, but the scanners and OpenHands will add to it. Recheck in M1-2 and M1-4.

## Follow-up

- Add a rule to M2-3 and M2-8: wait on an API call before treating the app as ready, and use a different loopback port for the verify container.
- None for the plan otherwise. No new tasks.
