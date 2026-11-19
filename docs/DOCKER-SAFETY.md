# Docker safety

These rules come from `CLAUDE.md`. They apply to every container we run.

## Rules

- **Containers only.** Juice Shop, the scanners, Jenkins and the OpenHands agent run only in containers. Never install or run Juice Shop or its dependencies directly on the Mac.
- **Loopback only.** Bind every published port to `127.0.0.1`. The vulnerable app must never be reachable from the network.
- **Label everything.** Every container, image, volume and network carries the label `project=governed-remediation`.
- **One clean-up command** removes everything with that label.
- **OpenHands sandbox.** Never use the unsandboxed local runtime. The agent's container may see a throwaway copy of the repo and nothing else from the Mac. No home folder mounts. No AWS credentials.
- **Pin versions.** Pin every image to a version.

## How the base Compose file helps

`compose.yaml` sets the project name, defines the isolated `project-net` network, and shows the label and the loopback port form. Copy the commented example when you add a service.

Ports use the form `127.0.0.1:<host-port>:<container-port>`. A port written as `8080:8080` is open to the network. Do not write it.

## Running the app

```
make up         # run Juice Shop on 127.0.0.1:3000, wait for the API
make check-up   # prove: bound to loopback only, no answer on the LAN address
make down       # remove the container
```

## Clean-up

```
make list       # show what carries the label
make clean-all  # remove it
```

`clean-all` removes containers, networks, volumes and images that carry `project=governed-remediation`. It also removes the images named in `spikes/pulled-images.txt`, and nothing else. Run `make list` first if you want to see what will go.

**Pulled images.** An image pulled from a registry carries no project label. Before you pull one, add it to `spikes/pulled-images.txt`, one per line, in the same form the Compose file uses: `repo:tag@sha256:digest`. An image pulled by digest has no plain tag, so `repo:tag` alone would not be found. `clean-all` then removes it by name.

Compose does not add our label by itself. A container you start with a plain `docker run` is only cleaned up if you pass `--label project=governed-remediation`.

## Not covered

The Docker build cache is not labelled and `clean-all` does not touch it. Pulled images that are not listed in `spikes/pulled-images.txt` stay.
