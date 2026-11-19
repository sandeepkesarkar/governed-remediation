#!/bin/sh
# Tests for scripts/scan.sh. It runs Semgrep three times (about 25 s each).
# 1. Semgrep fails (a rule set that does not exist): non-zero, and no SARIF is left behind.
# 2. The expected finding is missing: non-zero, with a message.
# 3. The normal run passes and writes SARIF to out/.
set -u
cd "$(dirname "$0")/.."
fail=0
check() { if [ "$1" = ok ]; then echo "PASS: $2"; else echo "FAIL: $2"; fail=1; fi; }

SCAN_RULESETS="p/this-rule-set-does-not-exist-xyz" scripts/scan.sh >/tmp/gr-scan-1.log 2>&1; rc=$?
[ "$rc" -ne 0 ] && check ok "Semgrep failure exits non-zero" || check bad "Semgrep failure exits non-zero"
grep -q "Semgrep exited with an error" /tmp/gr-scan-1.log && check ok "failure message is clear" || check bad "failure message is clear"
[ ! -f out/semgrep.sarif ] && check ok "no stale SARIF is left" || check bad "no stale SARIF is left"

SCAN_EXPECT_FILE="routes/does-not-exist.ts" scripts/scan.sh >/tmp/gr-scan-2.log 2>&1; rc=$?
[ "$rc" -ne 0 ] && check ok "missing expected finding exits non-zero" || check bad "missing expected finding exits non-zero"
grep -q "expected finding" /tmp/gr-scan-2.log && check ok "missing finding message is clear" || check bad "missing finding message is clear"

scripts/scan.sh >/tmp/gr-scan-3.log 2>&1; rc=$?
[ "$rc" -eq 0 ] && check ok "normal run passes" || check bad "normal run passes"
[ -s out/semgrep.sarif ] && check ok "SARIF written to out/" || check bad "SARIF written to out/"
grep -q "routes/login.ts" /tmp/gr-scan-3.log && check ok "login finding reported" || check bad "login finding reported"
git check-ignore -q out/semgrep.sarif && check ok "out/ is ignored by git" || check bad "out/ is ignored by git"
exit $fail
