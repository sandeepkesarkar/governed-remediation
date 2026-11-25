#!/bin/sh
# Step "verify" (specs/M2-thin-slice.md, section 2, step 6; plan M2-8). NO model call and no cost.
#
# Usage: scripts/verify.sh [PR]        (PR defaults to 13)
#
# Takes a fix pull request and produces evidence on whether it fixes the finding, then posts ONE comment on it
# (a second run updates that comment). It never merges and never decides. Everything is checked against the pull
# request's own branch, exported with "git archive" into out/verify. The branch is never checked out here.
# It is AI-written code from an issue, so it only ever runs in throwaway containers.
#
#   1. read     The pull request and the issue it closes (GITHUB_VERIFY_TOKEN). Fork pull requests are refused.
#   2. scope    The change list must be plain files in the folders the fix step may touch. If not, nothing from
#               the pull request is run, and the comment says so.
#   3. build    The pull request's app/ is built into a throwaway image with the same pinned build as "make build-app".
#   4. tests    A test container installs dependencies (scripts off), then is cut off from every network. In it:
#               the new spec on the fix (must pass), the whole server suite on the fix, then the new spec again with
#               the fixed files put back to main's unfixed versions (must FAIL: that proves the spec tells the two
#               apart). If the suite fails anywhere, main's code is run too, to separate new failures from old ones.
#   5. scan     The same Semgrep step as "make scan", on the pull request's app/. The finding must be gone.
#   6. exploit  A throwaway container of the build on its OWN internal network (no route out, no published port).
#               scripts/exploit.sh runs unchanged against it. A legitimate login is checked too.
#   7. comment  One evidence comment on the pull request, whatever the outcome, and a short linked summary on the
#               issue it closes. Both use GITHUB_VERIFY_TOKEN (Issues and Pull requests write, nothing else).
#
# It never touches the real app (gr-juice-shop), project-net or exploit-net. Every object it makes carries the
# project label and is removed on every way out of this script.
#
# Exit code: 0 all four checks passed, 1 something did not pass (the comment says what), 3 the comment was not posted.
set -u
cd "$(dirname "$0")/.."
. scripts/isolation.sh   # env_value
PY_IMAGE=${PY_IMAGE:-$(sed -n 's/^PY_IMAGE="\(.*\)"$/\1/p' scan/python.conf)}
NODE_REF=${NODE_REF:-$(sed -n 's/^NODE_REF *:= *//p' Makefile)}
LABEL='project=governed-remediation'
PR=${1:-13}
D=out/verify
REF=refs/verify/pr-$PR
IMAGE=governed-remediation/juice-shop:verify-pr$PR
TESTNET=gr-verify-testnet; NET=gr-verify-net; TESTC=gr-verify-tests; APPC=gr-verify-app

say() { echo "verify: $*"; }
die() { echo "verify: FAILED: $*" >&2; exit 1; }

case "$PR" in ''|*[!0-9]*) die "the pull request must be a number";; esac

clear_all() {
  docker rm -f -v "$TESTC" "$APPC" >/dev/null 2>&1
  docker network rm "$TESTNET" "$NET" >/dev/null 2>&1
  docker image rm -f "$IMAGE" >/dev/null 2>&1
  git update-ref -d "$REF" 2>/dev/null
  rm -rf "$D/pr" "$D/base"
  true
}
trap clear_all EXIT
trap 'exit 1' INT TERM

docker info >/dev/null 2>&1 || die "Docker is not running. Start Rancher Desktop: rdctl start"
[ -n "$(env_value GITHUB_VERIFY_TOKEN)" ] || die "GITHUB_VERIFY_TOKEN is not set (names are in .env.example)"
NODE_REF=${NODE_REF:?}
remote=$(git remote get-url origin 2>/dev/null) || die "no git remote named origin"
repo=$(printf '%s' "$remote" | sed -e 's#^git@github.com:##' -e 's#^https://github.com/##' -e 's#\.git$##')

# Our own Python tooling runs in the pinned container. The token goes in by name only, and only where it is needed.
py() {   # no token. PYNET puts it on one network (the login check must reach the throwaway app).
  docker run --rm --label "$LABEL" ${PYNET:+--network "$PYNET"} -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD/agents:/repo/agents:ro" -v "$PWD/$D:/repo/$D" -w /repo "$PY_IMAGE" python -m "$@"
}
pyt() {  # with the GitHub token
  GITHUB_VERIFY_TOKEN=$(env_value GITHUB_VERIFY_TOKEN) docker run --rm --label "$LABEL" -e GITHUB_VERIFY_TOKEN -e PYTHONDONTWRITEBYTECODE=1 \
    -v "$PWD/agents:/repo/agents:ro" -v "$PWD/$D:/repo/$D" -w /repo "$PY_IMAGE" python -m "$@"
}

clear_all
rm -rf "$D"; mkdir -p "$D"

# ---- 1. read ----
say "reading pull request #$PR from $repo"
pyt agents.verify_agent.evidence pr-info --repo "$repo" --pr "$PR" --dir "$D" \
  || die "cannot verify this pull request (nothing was posted)"
HEAD_SHA=$(sed -n 's/.*"head_sha": *"\([0-9a-f]*\)".*/\1/p' "$D/pr.json")

git fetch -q origin main "+refs/pull/$PR/head:$REF" 2>/dev/null || die "cannot fetch the pull request's branch"
[ "$(git rev-parse "$REF")" = "$HEAD_SHA" ] || die "the pull request changed while it was being fetched. Run again"
git rev-parse origin/main > "$D/base-sha.txt"
git rev-list --count "$REF..origin/main" > "$D/behind.txt"

# ---- 2. scope ----
git diff --raw --no-renames "origin/main...$REF" > "$D/diff.raw" || die "cannot read the pull request's change list"
SCOPE_OK=1
py agents.verify_agent.evidence scope --dir "$D" || SCOPE_OK=0
mkdir -p "$D/base"
git archive origin/main app | tar -x -C "$D/base" || die "cannot export main's app/"

if [ "$SCOPE_OK" = 1 ]; then
  mkdir -p "$D/pr"
  git archive "$REF" app | tar -x -C "$D/pr" || die "cannot export the pull request's app/"
  say "exported the pull request's app/ at $HEAD_SHA (not checked out)"

  # ---- 3. build ----
  say "building a throwaway image of the pull request (several minutes)"
  make --no-print-directory build-app JS_IMAGE="$IMAGE" APP_DIR="$D/pr/app" > "$D/build.log" 2>&1
  echo $? > "$D/build.rc"
  [ "$(cat "$D/build.rc")" = 0 ] && say "build ok" || say "build FAILED (see the comment)"

  # ---- 4. tests ----
  say "starting the test container (dependencies are installed with scripts off, then the network is cut)"
  docker network create --label "$LABEL" "$TESTNET" >/dev/null || die "cannot create the test network"
  docker run -d --name "$TESTC" --label "$LABEL" --network "$TESTNET" \
    --cap-drop ALL --security-opt no-new-privileges --memory 3g --pids-limit 1024 \
    --entrypoint sleep "$NODE_REF" infinity >/dev/null || die "cannot start the test container"
  COPYFILE_DISABLE=1 tar --no-xattrs -C "$D/pr/app" --exclude=node_modules -cf - . \
    | docker exec -i "$TESTC" sh -c 'mkdir -p /workspace/app && tar -x --no-same-owner -C /workspace/app' \
    || die "copying the pull request into the test container failed"
  docker exec "$TESTC" sh -c 'cd /workspace/app && timeout 900 npm install --ignore-scripts --no-audit --no-fund --loglevel=error \
    && for m in sqlite3 libxmljs2; do (cd node_modules/$m && npm_config_nodedir=/usr/local timeout 600 npm run install) || exit 1; done' > "$D/tests-install.log" 2>&1
  echo $? > "$D/tests-install.rc"
  docker network disconnect "$TESTNET" "$TESTC" >/dev/null 2>&1
  nets=$(docker inspect -f '{{len .NetworkSettings.Networks}}' "$TESTC" 2>/dev/null)
  if [ "$(cat "$D/tests-install.rc")" = 0 ] && [ "$nets" = 0 ]; then
    TESTS=$(tr '\n' ' ' < "$D/changed-tests.txt")
    run_mocha() {  # name, then the mocha arguments. Output and exit code go to files.
      _n=$1; shift
      docker exec "$TESTC" sh -c "cd /workspace/app && timeout 900 npx mocha -r tsx $* 2>&1" > "$D/$_n.txt"
      echo $? > "$D/$_n.rc"
    }
    say "tests: the new spec on the fix"
    run_mocha spec-after "$TESTS"
    say "tests: the whole server suite on the fix"
    run_mocha suite-pr --recursive "'test/server/**/*.ts'"
    say "tests: the new spec on main's unfixed code"
    for f in $(cat "$D/changed-sources.txt"); do   # paths were checked by the scope step: plain, safe names
      if [ -f "$D/base/app/$f" ]; then docker cp "$D/base/app/$f" "$TESTC:/workspace/app/$f"
      else docker exec "$TESTC" rm -f "/workspace/app/$f"; fi
    done
    run_mocha spec-before "$TESTS"
    if [ "$(cat "$D/suite-pr.rc")" != 0 ]; then
      say "tests: the suite failed on the fix, so main's own code is run for comparison"
      for f in $(cat "$D/changed-tests.txt"); do
        if [ -f "$D/base/app/$f" ]; then docker cp "$D/base/app/$f" "$TESTC:/workspace/app/$f"
        else docker exec "$TESTC" rm -f "/workspace/app/$f"; fi
      done
      run_mocha suite-base --recursive "'test/server/**/*.ts'"
    fi
  else
    say "tests NOT run (install exit $(cat "$D/tests-install.rc"), networks left on the test container: $nets)"
  fi
  docker rm -f -v "$TESTC" >/dev/null 2>&1

  # ---- 5. scan ----
  say "re-scanning the pull request's app/ (same Semgrep step as make scan)"
  SCAN_APP="$D/pr/app" SCAN_OUT_DIR="$D" SCAN_OUTPUT_FILE=semgrep-pr.sarif SCAN_NO_EXPECT=1 scripts/scan.sh > "$D/scan.log" 2>&1
  echo $? > "$D/scan.rc"
  tail -n 2 "$D/scan.log"

  # ---- 6. exploit ----
  if [ "$(cat "$D/build.rc")" = 0 ]; then
    REAL_BEFORE=$(docker inspect -f '{{.Id}} {{.State.StartedAt}}' gr-juice-shop 2>/dev/null)
    say "starting the throwaway app on its own internal network (no route out, no published port)"
    docker network create --internal --label "$LABEL" "$NET" >/dev/null || die "cannot create the exploit network"
    docker run -d --name "$APPC" --label "$LABEL" --network "$NET" --network-alias juice-shop-prod \
      --cap-drop ALL --security-opt no-new-privileges --memory 1g --pids-limit 512 "$IMAGE" >/dev/null \
      || die "cannot start the throwaway app"
    PYNET="$NET" py agents.verify_agent.login_check --out "$D/login-check.json" --wait 120 2>&1 | sed 's/^/verify: /'
    docker network inspect "$NET" >/dev/null 2>&1 || die "the exploit network disappeared"
    if [ "$(sed -n 's/.*"status": *\([0-9a-z]*\).*/\1/p' "$D/login-check.json" 2>/dev/null)" != null ]; then
      EXPLOIT_NETWORK="$NET" EXPLOIT_APP="$APPC" scripts/exploit.sh --out "$D/exploit.json"
      echo $? > "$D/exploit.rc"
    fi
    docker logs --tail 40 "$APPC" > "$D/app.log" 2>&1
    REAL_AFTER=$(docker inspect -f '{{.Id}} {{.State.StartedAt}}' gr-juice-shop 2>/dev/null)
    if [ -z "$REAL_BEFORE" ]; then say "the real app was not running (nothing to disturb)"
    elif [ "$REAL_BEFORE" = "$REAL_AFTER" ]; then say "the real app container was not touched"
    else echo "verify: WARNING: the real app container changed during this run" >&2; fi
  fi
fi
clear_all

# ---- 7. comment ----
say "writing and posting the evidence comment"
# VERIFY_NO_POST=1 writes the comment to out/verify/comment.md and posts nothing (for trying the script out).
pyt agents.verify_agent.evidence report --dir "$D" --repo "$repo" --pr "$PR" ${VERIFY_NO_POST:+} $([ "${VERIFY_NO_POST:-0}" = 1 ] || echo --post)
exit $?
