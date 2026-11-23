#!/bin/sh
# Step "ticket" (specs/M2-thin-slice.md, section 2, step 3).
# Reads the SARIF file from the scan step and creates one GitHub issue for the slice's
# finding, or finds the one that already exists. A second run creates nothing.
# The finding is the same one the scan step expects (scan/semgrep.conf). Override from the
# environment: SCAN_EXPECT_FILE (default routes/login.ts) and SCAN_EXPECT_CWE (default CWE-89).
#
# The token is the variable GITHUB_TOKEN (the name is in .env.example). If it is not in the
# environment, only that one line is taken from .env. The value is never printed and goes to
# the container through the environment, not the command line.
# The repo (owner/name) comes from the git remote "origin". The links use the commit at HEAD.
set -u
cd "$(dirname "$0")/.."
. scan/semgrep.conf
PY_IMAGE=${PY_IMAGE:-$(sed -n 's/^PY_IMAGE="\(.*\)"$/\1/p' scan/python.conf)}
EXPECT_FILE=${SCAN_EXPECT_FILE:-$EXPECT_FILE_DEFAULT}
EXPECT_CWE=${SCAN_EXPECT_CWE:-$EXPECT_CWE_DEFAULT}
SARIF=out/$OUTPUT_FILE

die() { echo "ticket: FAILED: $1" >&2; exit 1; }

[ -f "$SARIF" ] || die "no SARIF file at $SARIF. Run: make scan"

if [ -z "${GITHUB_TOKEN:-}" ] && [ -f .env ]; then
  GITHUB_TOKEN=$(sed -n 's/^GITHUB_TOKEN=//p' .env | head -n 1 | tr -d "\"'\r")
fi
[ -n "${GITHUB_TOKEN:-}" ] || die "GITHUB_TOKEN is not set. Put it in .env (names are in .env.example)"
export GITHUB_TOKEN

remote=$(git remote get-url origin 2>/dev/null) || die "no git remote named origin"
repo=$(printf '%s' "$remote" | sed -e 's#^git@github.com:##' -e 's#^https://github.com/##' -e 's#\.git$##')
commit=$(git rev-parse HEAD 2>/dev/null) || die "this is not a git checkout"

# The container has the network (the API is on the internet) and no ports. The code and the
# SARIF are mounted read-only. Only the variable name is given, so the value is not in the command.
docker run --rm --label project=governed-remediation \
  -e GITHUB_TOKEN \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/agents:/repo/agents:ro" -v "$PWD/out:/repo/out:ro" -v "$PWD/app:/repo/app:ro" -w /repo \
  "$PY_IMAGE" python -m agents.ticket_agent.ticket "/repo/$SARIF" \
  --repo "$repo" --commit "$commit" --only "$EXPECT_FILE:$EXPECT_CWE"
