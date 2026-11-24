# Project label. Every container, image, volume and network we create carries it.
LABEL_KEY   := project
LABEL_VALUE := governed-remediation
FILTER      := label=$(LABEL_KEY)=$(LABEL_VALUE)
# Images pulled from a registry carry no label. They are listed here and removed by name.
PULLED      := spikes/pulled-images.txt

.PHONY: help list clean-all diagrams build-app up down check-up test-up scan test test-scan scan-secrets ticket exploit test-network-isolation

help:
	@echo "make list       Show everything labelled $(LABEL_KEY)=$(LABEL_VALUE)"
	@echo "make clean-all  Remove every labelled container, network, volume and image"
	@echo "make diagrams   Render docs/images/src/*.mmd to SVG in a pinned mermaid container"
	@echo "make build-app  Build the Juice Shop image from app/ (pinned base images)"
	@echo "make up         Step up: run the app on 127.0.0.1 and wait for the API to answer"
	@echo "make down       Stop and remove the app container"
	@echo "make check-up   Prove the app is on loopback only (run after make up)"
	@echo "make test-up    Test the up step (needs the image from make build-app)"
	@echo "make test-network-isolation  Prove exploit-net has no route out (run after make up)"
	@echo "make scan       Step scan: Semgrep on app/, SARIF to out/"
	@echo "make ticket     Step ticket: one GitHub issue for the slice's finding (needs GITHUB_TOKEN, run make scan first)"
	@echo "make exploit    Step exploit: run the login SQLi exploit, container-to-container (run make up first)"
	@echo "make test       Run the Python tests with coverage (at least 90 percent)"
	@echo "make scan-secrets  Secrets scan of the tracked files (gitleaks, path allowlist in .gitleaks.toml)"
	@echo "make test-scan  Test the failure cases of the scan step (runs Semgrep three times)"

list:
	@echo "== containers"; docker ps -a --filter "$(FILTER)" --format '{{.ID}}  {{.Names}}  {{.Image}}'
	@echo "== networks";   docker network ls --filter "$(FILTER)" --format '{{.ID}}  {{.Name}}'
	@echo "== volumes";    docker volume ls --filter "$(FILTER)" --format '{{.Name}}'
	@echo "== images";     docker image ls -a --filter "$(FILTER)" --format '{{.ID}}  {{.Repository}}:{{.Tag}}'

# Removes only objects that carry the project label. Order matters:
# containers first, then networks and volumes, then images.
clean-all:
	@ids=$$(docker ps -aq --filter "$(FILTER)"); \
	  if [ -n "$$ids" ]; then docker rm -f -v $$ids; fi
	@ids=$$(docker network ls -q --filter "$(FILTER)"); \
	  if [ -n "$$ids" ]; then docker network rm $$ids; fi
	@ids=$$(docker volume ls -q --filter "$(FILTER)"); \
	  if [ -n "$$ids" ]; then docker volume rm -f $$ids; fi
	@ids=$$(docker image ls -aq --filter "$(FILTER)"); \
	  if [ -n "$$ids" ]; then docker image rm -f $$ids; fi
	@# Pulled images carry no label, so remove them by name from the list.
	@grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$$' $(PULLED) 2>/dev/null | while read -r img; do \
	  if docker image inspect "$$img" >/dev/null 2>&1; then docker image rm -f "$$img"; fi; \
	done; true
	@echo "clean-all done. Remaining labelled objects:"
	@$(MAKE) --no-print-directory list

# Renders each docs/images/src/*.mmd to docs/images/*.svg. The mermaid sources are the
# single source. The container is labelled, has no published ports and sees only docs/images.
# Each run leaves a stopped, labelled container. "make clean-all" removes them.
MERMAID_IMAGE := ghcr.io/mermaid-js/mermaid-cli/mermaid-cli:11.12.0@sha256:bad64c9d9ad917c8dfbe9d9e9c162b96f6615ff019b37058638d16eb27ce7783
diagrams:
	@for f in docs/images/src/*.mmd; do \
	  n=$$(basename $$f .mmd); \
	  docker run --label $(LABEL_KEY)=$(LABEL_VALUE) -v "$(CURDIR)/docs/images:/data" $(MERMAID_IMAGE) \
	    -p /data/src/puppeteer.json -i /data/src/$$n.mmd -o /data/$$n.svg -b white || exit 1; \
	done

# Builds the Juice Shop image from app/ with upstream's Dockerfile, unchanged.
# The two base images the Dockerfile names are pinned by digest here, with named build
# contexts, so nothing inside app/ is edited. The image carries the project label.
JS_IMAGE      := governed-remediation/juice-shop:v20.0.0-local
JS_COMMIT     := f356a09207c7a9550eb6fc4c3945e081922cf998
NODE_BASE     := docker-image://docker.io/library/node:24@sha256:9d266751ca3d7fdbe651c878ffd5ad0a42fed49a18c283509267c97f025b7496
DISTROLESS    := docker-image://gcr.io/distroless/nodejs24-debian13@sha256:24bc0fe0225c7518f202a822587dad74fe143b96326b81fe5cc08c1df8bed03e
build-app:
	docker build --label $(LABEL_KEY)=$(LABEL_VALUE) \
	  --build-context node:24=$(NODE_BASE) \
	  --build-context gcr.io/distroless/nodejs24-debian13=$(DISTROLESS) \
	  --build-arg VCS_REF=$(JS_COMMIT) --build-arg BUILD_DATE=2026-11-18 \
	  -t $(JS_IMAGE) app

# Step "up" (specs/M2-thin-slice.md). Builds the image first if it is missing.
up:
	@docker image inspect $(JS_IMAGE) >/dev/null 2>&1 || $(MAKE) --no-print-directory build-app
	@scripts/up.sh

down:
	@docker compose -f compose.yaml down --remove-orphans

check-up:
	@scripts/check-loopback.sh

test-up:
	@tests/up-test.sh

# Step "scan" (specs/M2-thin-slice.md). Output goes to out/, which git ignores.
scan:
	@scripts/scan.sh

# Python tests with coverage, in the pinned Python image, in a labelled container.
# The repo is mounted read-only. Dependencies go to a folder inside the container.
PY_IMAGE := python:3.13.18-alpine3.24@sha256:9ef1a599f863231c3d91e941389bfdc4a2d6070557243d54df1a4e57015b960e
test:
	@docker run --rm --label $(LABEL_KEY)=$(LABEL_VALUE) -v "$(CURDIR):/repo:ro" -w /repo \
	  -e PYTHONDONTWRITEBYTECODE=1 -e COVERAGE_FILE=/tmp/.coverage -e PYTHONPATH=/tmp/deps \
	  $(PY_IMAGE) sh -c 'pip install -q --root-user-action=ignore --no-cache-dir --target /tmp/deps -r requirements-dev.txt \
	  && python -m pytest -q --cov --cov-config=.coveragerc --cov-report=term-missing'

test-scan:
	@tests/scan-test.sh

# Step "ticket" (specs/M2-thin-slice.md). Needs out/semgrep.sarif (make scan) and GITHUB_TOKEN.
ticket:
	@scripts/ticket.sh

# Step "exploit" (specs/M2-thin-slice.md). Needs the app running (make up). Runs as a
# one-off container on the egress-free exploit-net network (compose.yaml).
exploit:
	@scripts/exploit.sh

test-network-isolation:
	@tests/network-isolation-test.sh

scan-secrets:
	@scripts/scan-secrets.sh
