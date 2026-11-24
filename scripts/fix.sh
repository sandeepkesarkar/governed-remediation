#!/bin/sh
# Step "fix" (specs/M2-thin-slice.md, section 2, step 5; plan M2-7). PAID: one OpenHands run on the Anthropic API.
#
# Usage: scripts/fix.sh [--dry-run] [ISSUE]     (ISSUE defaults to 3)
#
# What happens, in order:
#   1. task     A python container reads the issue (token GITHUB_TOKEN, read use) and writes the task.
#   2. sandbox  The pinned OpenHands agent-server runs in a container with NO mounts, NO published ports and NO
#               credentials. A throwaway copy of app/ (without frontend/ and node_modules) is streamed in with
#               tar. The dependencies are installed there by this script, not by the agent.
#   3. run      The client container (holds ANTHROPIC_API_KEY, never a GitHub token) runs one OpenHands
#               conversation with a dollar cap and an iteration cap, then the sanity check. No model in the check.
#   4. check    The script inspects the containers and fails if any credential is in the sandbox.
#   5. publish  A plain python script (no model) turns the allowed changed files into a branch and a pull request
#               with GITHUB_FIX_TOKEN. The agent never sees that token. Nothing is merged.
#   6. cost     One line is appended to out/cost-log.jsonl and the run and running totals are printed.
#
# --dry-run does steps 1, 2 and 4 on the pristine copy and the baseline specs. It makes no model call, needs no
# Anthropic key and no fix token, and writes no cost line. A run that stops before the model is called writes none either.
#
# The whole run is limited to FIX_WALL_SECONDS (default 900). The cost cap and the iteration cap are enforced by
# OpenHands inside the run. The wall clock is a separate backstop in case cost reporting stalls.
#
# Tokens come from the environment or, if absent, from .env (one line each). Values are never printed and never
# appear on a command line: they reach a container through the environment, by name only.
set -u
cd "$(dirname "$0")/.."
. scan/semgrep.conf
PY_IMAGE=${PY_IMAGE:-$(sed -n 's/^PY_IMAGE="\(.*\)"$/\1/p' scan/python.conf)}
SERVER_IMAGE='ghcr.io/openhands/agent-server:1.63.1-python@sha256:506c2e243dcc3f5092ad0909c5dff9fef621298faed9042b5d4b0375fac837a5'
CLIENT_IMAGE='governed-remediation/fixer-client:1.63.1'
LABEL='project=governed-remediation'
NET=gr-fixer-net; SANDBOX=gr-fixer-sandbox; CLIENT=gr-fixer-client
WALL=${FIX_WALL_SECONDS:-900}
FIX_DIR=out/fix
LOG=out/cost-log.jsonl

DRY=0
[ "${1:-}" = "--dry-run" ] && { DRY=1; shift; }
ISSUE=${1:-3}
EXPECT="app/$EXPECT_FILE_DEFAULT:$EXPECT_CWE_DEFAULT"

OUTCOME=error; RC=1; MODEL_CALLED=0; RECORDED=0; WATCHDOG=

say() { echo "fix: $*"; }
die() { echo "fix: FAILED: $*" >&2; RC=1; exit 1; }

. scripts/isolation.sh   # env_value and isolation_check (tested by tests/isolation-test.sh)

clear_containers() {
  docker rm -f -v "$CLIENT" "$SANDBOX" >/dev/null 2>&1
  docker network rm "$NET" >/dev/null 2>&1
  true
}

cleanup() {
  [ -n "$WATCHDOG" ] && kill "$WATCHDOG" 2>/dev/null
  clear_containers
}

record_cost() {  # runs once, on every way out, if the model was called or the call was tried
  [ "$MODEL_CALLED" = 1 ] || return 0
  [ "$RECORDED" = 1 ] && return 0
  RECORDED=1
  mkdir -p out
  docker run --rm --label "$LABEL" -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD/agents:/repo/agents:ro" -v "$PWD/out:/repo/out" -w /repo "$PY_IMAGE" \
    python -m agents.fixer_agent.costlog record --log "$LOG" --issue "$ISSUE" --outcome "$OUTCOME" \
    --metrics "$FIX_DIR/metrics.json" --isolation "$ISOLATION" || { [ "$RC" = 0 ] && RC=3; }
}

on_exit() { cleanup; record_cost; exit "$RC"; }
on_term() { OUTCOME=timeout; RC=1; echo "fix: stopped: wall-clock limit of $WALL seconds" >&2; exit 1; }
trap on_exit EXIT
trap on_term TERM INT

# Before the run: a problem stops everything.
assert_isolated() {  # name, then the exact variable names this container may hold
  reason=$(isolation_check "$@") || die "isolation: $reason"
}

# After the run: the result goes into ISOLATION, and from there into the cost log (--isolation), so a real
# failure shows up as its own outcome and cannot pass for the run's outcome. Only GPG_KEY (set by the python base
# image: Python's public release-signing key) and the Anthropic key are allowed, and only on the client.
ISOLATION=not_checked
check_isolation_after() {
  if ! docker inspect "$SANDBOX" >/dev/null 2>&1 || ! docker inspect "$CLIENT" >/dev/null 2>&1; then
    ISOLATION="not_checked (a container was already gone)"; return 0
  fi
  if ! r=$(isolation_check "$SANDBOX"); then ISOLATION="FAILED: sandbox: $r"; return 1; fi
  if ! r=$(isolation_check "$CLIENT" ANTHROPIC_API_KEY GPG_KEY); then ISOLATION="FAILED: client: $r"; return 1; fi
  ISOLATION=passed
}

# ---- before anything is spent or started ----
docker info >/dev/null 2>&1 || die "Docker is not running. Start Rancher Desktop: rdctl start"
mkdir -p out
[ -n "$(env_value GITHUB_TOKEN)" ] || die "GITHUB_TOKEN is not set (names are in .env.example)"
if [ "$DRY" = 0 ]; then
  [ -n "$(env_value ANTHROPIC_API_KEY)" ] || die "ANTHROPIC_API_KEY is not set (names are in .env.example)"
  [ -n "$(env_value GITHUB_FIX_TOKEN)" ] || die "GITHUB_FIX_TOKEN is not set. Create it first (see docs/ENVIRONMENT.md) and put it in .env"
fi
remote=$(git remote get-url origin 2>/dev/null) || die "no git remote named origin"
repo=$(printf '%s' "$remote" | sed -e 's#^git@github.com:##' -e 's#^https://github.com/##' -e 's#\.git$##')
git fetch -q origin main 2>/dev/null || die "cannot fetch origin/main"
git diff --quiet origin/main -- app/ || die "app/ differs from origin/main. The pull request is made against main, so the copy must match it"
docker image inspect "$CLIENT_IMAGE" >/dev/null 2>&1 || die "the client image is missing. Run: make build-fixer-client"
case "$ISSUE" in ''|*[!0-9]*) die "the issue must be a number";; esac

( sleep "$WALL"; kill -TERM $$ 2>/dev/null; docker rm -f "$CLIENT" "$SANDBOX" >/dev/null 2>&1 ) &
WATCHDOG=$!

# ---- 1. task ----
rm -rf "$FIX_DIR"; mkdir -p "$FIX_DIR"
say "reading issue #$ISSUE from $repo"
GITHUB_TOKEN=$(env_value GITHUB_TOKEN) docker run --rm --label "$LABEL" -e GITHUB_TOKEN -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/agents:/repo/agents:ro" -v "$PWD/$FIX_DIR:/repo/$FIX_DIR" -w /repo "$PY_IMAGE" \
  python -m agents.fixer_agent.task --repo "$repo" --issue "$ISSUE" --expect "$EXPECT" --out "$FIX_DIR/task.json" \
  || die "the task step failed"

# ---- 2. sandbox ----
clear_containers
docker network create --label "$LABEL" "$NET" >/dev/null || die "cannot create the network"
docker run -d --name "$SANDBOX" --label "$LABEL" --network "$NET" \
  --cap-drop ALL --security-opt no-new-privileges --memory 3g --pids-limit 1024 \
  "$SERVER_IMAGE" --host 0.0.0.0 >/dev/null || die "cannot start the sandbox"
i=0
until docker run --rm --network "$NET" --label "$LABEL" "$CLIENT_IMAGE" python -c \
  "import urllib.request as u;u.urlopen('http://$SANDBOX:8000/health',timeout=2)" >/dev/null 2>&1; do
  i=$((i+1)); [ "$i" -lt 45 ] || die "the sandbox did not become ready"; sleep 2
done
assert_isolated "$SANDBOX"
say "isolation (before): sandbox has no credential variables, no mounts, no published ports, label set"

say "copying a throwaway app/ into the sandbox (no frontend, no node_modules)"
COPYFILE_DISABLE=1 tar --no-xattrs -C app --exclude=./frontend --exclude=node_modules -cf - . \
  | docker exec -i "$SANDBOX" sh -c 'mkdir -p /workspace/app && tar -x -C /workspace/app' || die "copy failed"
say "installing dependencies in the sandbox (about 3 minutes, no agent involved)"
docker exec "$SANDBOX" sh -c 'cd /workspace/app && npm install --ignore-scripts --no-audit --no-fund --loglevel=error >/dev/null 2>&1' \
  || die "npm install failed in the sandbox"
# The sandbox's npm blocks install scripts, and "npm rebuild" then does nothing and still says it worked. So the
# one native module the tests need is built by running its own install script directly.
say "building the sqlite3 native module"
docker exec "$SANDBOX" sh -c 'cd /workspace/app/node_modules/sqlite3 && npm run install 2>&1 | tail -3' \
  || die "building sqlite3 failed in the sandbox"
say "baseline: Juice Shop's own specs on the untouched copy"
base_out=$(docker exec "$SANDBOX" sh -c 'cd /workspace/app && npx mocha -r tsx test/server/insecuritySpec.ts test/server/currentUserSpec.ts 2>&1'); base_rc=$?
printf '%s\n' "$base_out" | grep -E "passing|failing"
[ "$base_rc" = 0 ] || die "the baseline specs do not pass on the untouched copy"
# The check that was missing before: load the app's own database layer (models/index, sequelize, sqlite3) and
# run one query. The regression test needs exactly this, and the two specs above do not touch the database.
say "baseline: the app's database layer loads and answers a query"
docker exec -i "$SANDBOX" sh -c 'cat > /tmp/dbcheck.ts' <<'TS'
import * as models from '/workspace/app/models/index'
models.sequelize.query('SELECT 1 AS x', { plain: true })
  .then((r: any) => { if (r?.x !== 1) { console.error('unexpected answer'); process.exit(1) } console.log('database layer ok (models/index, sequelize, sqlite3)'); process.exit(0) })
  .catch((e: Error) => { console.error('database layer failed: ' + e.message.split('\n')[0]); process.exit(1) })
TS
docker exec "$SANDBOX" sh -c 'cd /workspace/app && npx tsx /tmp/dbcheck.ts 2>&1 | tail -3; rc=$?; rm -f /tmp/dbcheck.ts data/juiceshop.sqlite; exit $rc' \
  | tee /dev/stderr | grep -q "database layer ok" || die "the app's database layer does not work in the sandbox"

if [ "$DRY" = 1 ]; then
  assert_isolated "$SANDBOX"
  OUTCOME=dry_run_ok; RC=0; say "dry run complete. No model call, no pull request, nothing logged"; exit 0
fi

# ---- 3. run (paid) ----
say "running OpenHands: model anthropic/claude-sonnet-5-5, cap \$1.00 and 40 iterations, wall clock ${WALL}s"
MODEL_CALLED=1; OUTCOME=error
ANTHROPIC_API_KEY=$(env_value ANTHROPIC_API_KEY) docker run --name "$CLIENT" --label "$LABEL" --network "$NET" \
  -e ANTHROPIC_API_KEY -e "AGENT_HOST=http://$SANDBOX:8000" -e PYTHONPATH=/repo \
  -v "$PWD/agents:/repo/agents:ro" -v "$PWD/$FIX_DIR:/out" "$CLIENT_IMAGE" \
  python -m agents.fixer_agent.fix_run --task /out/task.json --out /out
run_rc=$?
OUTCOME=$(sed -n 's/.*"outcome": *"\([a-z_]*\)".*/\1/p' "$FIX_DIR/result.json" 2>/dev/null | head -n 1)
[ -n "$OUTCOME" ] || OUTCOME=error

# ---- 4. check ----
if check_isolation_after; then
  say "isolation (after): $ISOLATION. The sandbox holds no credential, mount or port. The client held only the Anthropic key"
else
  die "isolation FAILED after the run: ${ISOLATION#FAILED: }"
fi

[ "$run_rc" = 0 ] && [ "$OUTCOME" = ready ] || die "the run did not produce a fix that passes the sanity check (outcome: $OUTCOME)"

docker exec "$SANDBOX" tar -C /workspace/app --exclude=./node_modules -cf - . > "$FIX_DIR/tree.tar" || die "cannot copy the result out"
clear_containers

# ---- 5. publish ----
say "opening the pull request (no model, token GITHUB_FIX_TOKEN)"
GITHUB_FIX_TOKEN=$(env_value GITHUB_FIX_TOKEN) docker run --rm --label "$LABEL" -e GITHUB_FIX_TOKEN -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/agents:/repo/agents:ro" -v "$PWD/app:/repo/app:ro" -v "$PWD/$FIX_DIR:/repo/$FIX_DIR" -w /repo "$PY_IMAGE" \
  python -m agents.fixer_agent.publish --repo "$repo" --task "$FIX_DIR/task.json" --tree "$FIX_DIR/tree.tar" \
  --app-dir app --metrics "$FIX_DIR/metrics.json" --sanity "$FIX_DIR/sanity.json" --pr-out "$FIX_DIR/pr.json" \
  || { OUTCOME=publish_failed; die "publishing failed"; }
OUTCOME=pr_opened; RC=0
say "done. The pull request stays open and is NOT merged. It waits for the verify step (M2-8)"
exit 0
