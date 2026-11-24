#!/bin/sh
# Tests for scripts/check-banned-terms.sh. They use temporary terms files under out/ and never read
# .banned-terms.local. About 5 container runs, a few seconds each.
#  1. no terms file: exit 2 and a message
#  2. a file with only comments and blank lines: exit 2 (nothing was checked)
#  3. a term nobody uses: exit 0
#  4. a term that is in tracked files outside app/: exit 1, prints file:line, never the term or the line text
#  5. a term that is only in app/: exit 0 (app/ is not checked)
#  6. a term that matches a file name: exit 1
#  7. case is ignored, and a Windows line ending in the terms file does not break the match
set -u
cd "$(dirname "$0")/.."
fail=0
check() { if [ "$1" = ok ]; then echo "PASS: $2"; else echo "FAIL: $2"; fail=1; fi; }
mkdir -p out
T=out/.banned-test-terms
trap 'rm -f "$T" out/.banned-test.log' EXIT

BANNED_TERMS_FILE=out/does-not-exist scripts/check-banned-terms.sh >out/.banned-test.log 2>&1; rc=$?
[ "$rc" -eq 2 ] && check ok "missing terms file exits 2" || check bad "missing terms file exits 2 (got $rc)"
grep -q "Nothing was checked" out/.banned-test.log && check ok "missing file message is clear" || check bad "missing file message is clear"

printf '# only a comment\n\n   \n' > "$T"
BANNED_TERMS_FILE=$T scripts/check-banned-terms.sh >out/.banned-test.log 2>&1; rc=$?
[ "$rc" -eq 2 ] && check ok "a file with no terms exits 2" || check bad "a file with no terms exits 2 (got $rc)"

# Terms are built from two pieces so this file does not contain them as text (the check scans this file too).
printf 'zz-term-that-nobody-%s\n' 'uses-qq' > "$T"
BANNED_TERMS_FILE=$T scripts/check-banned-terms.sh >out/.banned-test.log 2>&1; rc=$?
[ "$rc" -eq 0 ] && check ok "an unused term exits 0" || check bad "an unused term exits 0 (got $rc)"
grep -q "clean" out/.banned-test.log && check ok "clean message" || check bad "clean message"

printf 'Closes #\n' > "$T"      # appears in tracked docs outside app/
BANNED_TERMS_FILE=$T scripts/check-banned-terms.sh >out/.banned-test.log 2>&1; rc=$?
[ "$rc" -eq 1 ] && check ok "a used term exits 1" || check bad "a used term exits 1 (got $rc)"
grep -q "^match: .*:[0-9][0-9]* (term #1)" out/.banned-test.log && check ok "match is printed as file:line and term number" || check bad "match is printed as file:line and term number"
grep -q -i "closes #" out/.banned-test.log && check bad "the term or the line text leaked into the output" || check ok "the term and the line text are not printed"

printf 'totp_token_%s\n' 'required' > "$T"   # only in app/routes/login.ts
git grep -q -i "totp_token_""required" -- . ':!app' && check bad "test precondition: the term must be only in app/" || check ok "test precondition holds"
BANNED_TERMS_FILE=$T scripts/check-banned-terms.sh >out/.banned-test.log 2>&1; rc=$?
[ "$rc" -eq 0 ] && check ok "a term only in app/ is not found" || check bad "a term only in app/ is not found (got $rc)"

printf 'check-banned-terms\n' > "$T"    # the script's own file name
BANNED_TERMS_FILE=$T scripts/check-banned-terms.sh >out/.banned-test.log 2>&1; rc=$?
grep -q "file name, term #1" out/.banned-test.log && check ok "a file name match is found" || check bad "a file name match is found"

printf 'CLOSES #\r\n' > "$T"
BANNED_TERMS_FILE=$T scripts/check-banned-terms.sh >out/.banned-test.log 2>&1; rc=$?
[ "$rc" -eq 1 ] && check ok "case and a Windows line ending are handled" || check bad "case and a Windows line ending are handled (got $rc)"
exit $fail
