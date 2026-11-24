#!/bin/sh
# Tests for scripts/isolation.sh (the isolation check used by scripts/fix.sh). It starts small labelled
# containers, some of them built to fail, and checks the verdict. About 11 containers, a few seconds each.
set -u
cd "$(dirname "$0")/.."
. scripts/isolation.sh
PY_IMAGE=${PY_IMAGE:-$(sed -n 's/^PY_IMAGE="\(.*\)"$/\1/p' scan/python.conf)}
fail=0
check() { if [ "$1" = ok ]; then echo "PASS: $2"; else echo "FAIL: $2"; fail=1; fi; }
L=project=governed-remediation
N=gr-isotest
cleanup() { docker rm -f "$N" >/dev/null 2>&1; }
trap cleanup EXIT
start() { cleanup; docker run -d --name "$N" "$@" "$PY_IMAGE" sleep 120 >/dev/null; }
# The container "$N" is already running. The rest of the line is the list of allowed variable names.
expect_pass() { d=$1; shift; out=$(isolation_check "$N" "$@"); rc=$?
  if [ $rc -eq 0 ] && [ -z "$out" ]; then check ok "$d"; else check bad "$d ($out)"; fi; }
expect_fail() { d=$1; shift; out=$(isolation_check "$N" "$@"); rc=$?
  if [ $rc -ne 0 ] && [ -n "$out" ]; then check ok "$d"; else check bad "$d"; fi; }

# The python image itself sets GPG_KEY (Python's public release-signing key). So every case allows that one
# exact name, except the case that tests what happens when it is not allowed.
G=GPG_KEY
start --label $L
expect_fail "GPG_KEY fails when it is not allowed"
expect_pass "a clean labelled container passes (GPG_KEY allowed by exact name)" $G
start --label $L -e GITHUB_TOKEN=x
expect_fail "another credential name still fails when GPG_KEY is allowed" $G
start --label $L -e ANTHROPIC_API_KEY=k
expect_fail "the Anthropic key fails when it is not allowed" $G
expect_pass "the Anthropic key passes when allowed" $G ANTHROPIC_API_KEY
start --label $L -e GPG_KEY_EXTRA=pub
expect_fail "an allowance is for one whole name, not a prefix" $G
start --label $L -e HARMLESS=sekrit-value-12345
GITHUB_FIX_TOKEN=sekrit-value-12345 expect_fail "a token value hidden under a harmless name is found" $G
out=$(GITHUB_FIX_TOKEN=sekrit-value-12345 isolation_check "$N" $G 2>&1)
case "$out" in *sekrit*) check bad "no value is printed";; *) check ok "no value is printed";; esac
start --label $L -v "$PWD/tests:/m:ro"
expect_fail "a mount fails" $G
start
expect_fail "a missing project label fails" $G
start --label $L -p 127.0.0.1::9
expect_fail "a published port fails" $G
exit $fail
