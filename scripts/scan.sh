#!/bin/sh
# Step "scan" (specs/M2-thin-slice.md, section 2, step 2).
# Runs Semgrep on app/ in a labelled container and writes SARIF to out/. Then checks the
# result with the SARIF reader. It exits non-zero, with a message, if Semgrep crashes, no
# SARIF is written, the SARIF is empty or not valid JSON, or the expected finding is missing.
# Settings are in scan/semgrep.conf. The expected finding can be set from the environment:
#   SCAN_EXPECT_FILE (default routes/login.ts)   SCAN_EXPECT_CWE (default CWE-89)
#   SCAN_RULESETS (default: the six in the config; for tests only)
set -u
cd "$(dirname "$0")/.."
. scan/semgrep.conf

RULESETS=${SCAN_RULESETS:-$RULESETS}   # override is for the failure test
EXPECT_FILE=${SCAN_EXPECT_FILE:-$EXPECT_FILE_DEFAULT}
EXPECT_CWE=${SCAN_EXPECT_CWE:-$EXPECT_CWE_DEFAULT}
OUT=out/$OUTPUT_FILE
PY_IMAGE=${PY_IMAGE:-$(sed -n 's/^PY_IMAGE="\(.*\)"$/\1/p' scan/python.conf)}

die() { echo "scan: FAILED: $1" >&2; rm -f "$OUT"; exit 1; }   # never leave a result behind after a failure

mkdir -p out
rm -f "$OUT"    # a stale file must never pass for a new result

ARGS=""
for r in $RULESETS; do ARGS="$ARGS --config $r"; done
for e in $EXCLUDES; do ARGS="$ARGS --exclude $e"; done

# app/ is the scan root and is read-only. Only out/ is writable. No ports, no other mounts.
# Paths come out relative to the app root (routes/login.ts, not app/routes/login.ts).
# shellcheck disable=SC2086
docker run --rm --label project=governed-remediation \
  -e SEMGREP_ENABLE_VERSION_CHECK=0 \
  -v "$PWD/app:/src:ro" -v "$PWD/out:/out" -w /src \
  "$SEMGREP_IMAGE" \
  semgrep scan --metrics=off --disable-version-check --sarif --output "/$OUT" $ARGS . \
  >out/semgrep.log 2>&1 || { tail -n 5 out/semgrep.log >&2; die "Semgrep exited with an error (log: out/semgrep.log)"; }

[ -f "$OUT" ] || die "Semgrep wrote no SARIF file ($OUT)"

# Check and summarise with the reader. The repo is mounted read-only. Same pinned Python image.
docker run --rm --label project=governed-remediation \
  -v "$PWD/agents:/repo/agents:ro" -v "$PWD/out:/repo/out:ro" -w /repo \
  -e PYTHONDONTWRITEBYTECODE=1 \
  "$PY_IMAGE" python -m agents.ticket_agent.sarif "/repo/$OUT" --expect-file "$EXPECT_FILE" --expect-cwe "$EXPECT_CWE" \
  || die "the SARIF check failed"
echo "scan: ok. SARIF is in $OUT"
