#!/bin/sh
# Tests for scripts/isolation.sh (the isolation check used by scripts/fix.sh). It starts small labelled
# containers, some of them built to fail, and checks the verdict. It also tests saving the sandbox output and
# checks the structure of scripts/fix.sh against the standing rule. About 20 containers, a few seconds each.
set -u
cd "$(dirname "$0")/.."
. scripts/isolation.sh
. scripts/salvage.sh
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

# ---- the client's two mounts, allowed by exact destination and mode (and nothing else) ----
# fix.sh gives the client: /repo/agents read-only and /out read-write. The ceiling is the same list.
M="/repo/agents:ro /out:rw"
# A variable assigned in front of a shell function can stay set after the call in POSIX shells. So the setting is
# made and cleared explicitly here. (scripts/fix.sh sets it inside $( ), a subshell, where it cannot leak.)
with_mounts() { ISOLATION_MOUNTS="$M"; "$@"; unset ISOLATION_MOUNTS; }
mkdir -p out/.isotest-a out/.isotest-b
trap 'cleanup; rm -rf out/.isotest-a out/.isotest-b out/.isotest-salvage' EXIT
start --label $L -v "$PWD/out/.isotest-a:/repo/agents:ro" -v "$PWD/out/.isotest-b:/out"
with_mounts expect_pass "the client's two allowed mounts pass" $G
expect_fail "the same mounts fail when no mount is allowed (the sandbox check)" $G
start --label $L -v "$PWD/out/.isotest-a:/repo/agents:ro"
with_mounts expect_pass "having only one of the allowed mounts passes (the list is a ceiling)" $G
start --label $L -v "$PWD/out/.isotest-a:/repo/agents:ro" -v "$PWD/out/.isotest-b:/out" -v "$PWD/tests:/extra:ro"
with_mounts expect_fail "an unexpected third mount fails" $G
start --label $L -v "$PWD/out/.isotest-a:/repo/agents:rw"
with_mounts expect_fail "an allowed destination in the wrong mode (agents read-write) fails" $G
start --label $L -v "$PWD/out/.isotest-b:/out:ro"
with_mounts expect_fail "an allowed destination in the wrong mode (out read-only) fails" $G
start --label $L -v "$PWD/tests:/home/someone:ro"
with_mounts expect_fail "a home-folder style destination fails" $G
start --label $L -v "$PWD/out/.isotest-a:/repo/agents-extra:ro"
with_mounts expect_fail "an allowed destination is matched whole, not as a prefix" $G
start --label $L -v "$PWD/out/.isotest-a:/repo/agents:ro" -e GITHUB_TOKEN=x
with_mounts expect_fail "allowed mounts do not excuse a credential variable" $G

# ---- saving the sandbox output ----
rm -rf out/.isotest-salvage; mkdir -p out/.isotest-salvage
start --label $L
docker exec "$N" sh -c 'mkdir -p /workspace/app/routes /workspace/app/node_modules/x && echo fixed > /workspace/app/routes/login.ts && echo big > /workspace/app/node_modules/x/y.js'
if salvage_output "$N" out/.isotest-salvage/tree.tar; then check ok "the sandbox output is saved"; else check bad "the sandbox output is saved"; fi
tar -tf out/.isotest-salvage/tree.tar 2>/dev/null | grep -q "routes/login.ts" && check ok "the saved tar holds the work" || check bad "the saved tar holds the work"
tar -tf out/.isotest-salvage/tree.tar 2>/dev/null | grep -q "node_modules" && check bad "node_modules is left out" || check ok "node_modules is left out"
cleanup
rm -f out/.isotest-salvage/tree.tar
if salvage_output "$N" out/.isotest-salvage/tree.tar; then check bad "a missing sandbox returns failure and writes nothing"; else
  [ ! -e out/.isotest-salvage/tree.tar ] && [ ! -e out/.isotest-salvage/tree.tar.part ] && check ok "a missing sandbox returns failure and writes nothing" || check bad "a missing sandbox returns failure and writes nothing"; fi

# ---- the standing rule for scripts/fix.sh ----
# The isolation check after the run may only block publishing. It must never be able to cause the loss of the
# sandbox output. These checks read the script, so a later edit cannot quietly break the rule.
F=scripts/fix.sh
save_line=$(grep -n '^save_output$' $F | head -1 | cut -d: -f1)
check_line=$(grep -n '^if check_isolation_after' $F | head -1 | cut -d: -f1)
publish_line=$(grep -n 'agents.fixer_agent.publish' $F | head -1 | cut -d: -f1)
[ -n "$save_line" ] && [ -n "$check_line" ] && [ "$save_line" -lt "$check_line" ] && check ok "the output is saved before the isolation verdict" || check bad "the output is saved before the isolation verdict"
[ -n "$publish_line" ] && [ "$check_line" -lt "$publish_line" ] && check ok "the isolation verdict comes before publishing" || check bad "the isolation verdict comes before publishing"
body=$(sed -n '/^cleanup() {/,/^}/p' $F)
s1=$(printf '%s\n' "$body" | grep -n 'save_output' | head -1 | cut -d: -f1)
s2=$(printf '%s\n' "$body" | grep -n 'clear_containers' | head -1 | cut -d: -f1)
[ -n "$s1" ] && [ -n "$s2" ] && [ "$s1" -lt "$s2" ] && check ok "cleanup saves the output before it removes the sandbox (every exit path)" || check bad "cleanup saves the output before it removes the sandbox (every exit path)"
grep -n 'rm -rf "$FIX_DIR"' $F | grep -q 'tree.tar' && check ok "a saved tar is moved aside, not deleted, by the next run" || check bad "a saved tar is moved aside, not deleted, by the next run"
grep -n 'sleep "$WALL"' $F | grep -q 'SANDBOX' && check bad "the watchdog does not remove the sandbox" || check ok "the watchdog does not remove the sandbox"
exit $fail
