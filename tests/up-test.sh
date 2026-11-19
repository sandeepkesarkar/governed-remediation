#!/bin/sh
# Tests for scripts/up.sh. Written first. Needs the image from "make build-app".
# 1. Failure path: a wrong expected version must exit non-zero and leave no container.
# 2. Happy path: the app answers, the port is bound to 127.0.0.1 only, a second run replaces
#    the container (new container ID), and "make down" removes it.
set -u
cd "$(dirname "$0")/.."
fail=0
check() { if [ "$1" = ok ]; then echo "PASS: $2"; else echo "FAIL: $2"; fail=1; fi; }
running() { docker ps -aq --filter "label=project=governed-remediation" --filter "name=gr-juice-shop"; }

make --no-print-directory down >/dev/null 2>&1

# 1. Failure path
UP_EXPECT_VERSION=99.0.0 UP_TIMEOUT=20 scripts/up.sh >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && check ok "wrong version exits non-zero" || check bad "wrong version exits non-zero"
[ -z "$(running)" ] && check ok "failed run leaves no container" || check bad "failed run leaves no container"

# 2. Happy path
scripts/up.sh >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && check ok "up succeeds" || check bad "up succeeds"
id1=$(running)
bind=$(docker port gr-juice-shop 3000/tcp 2>/dev/null | sort -u)
[ "$bind" = "127.0.0.1:3000" ] && check ok "bound to 127.0.0.1 only ($bind)" || check bad "bound to 127.0.0.1 only ($bind)"
curl -fsS -m 5 http://127.0.0.1:3000/rest/admin/application-version | grep -q '"version":"20.0.0"' \
  && check ok "API answers with version 20.0.0" || check bad "API answers with version 20.0.0"
scripts/up.sh >/dev/null 2>&1
id2=$(running)
[ -n "$id2" ] && [ "$id1" != "$id2" ] && check ok "second run replaces the container" || check bad "second run replaces the container"
[ "$(echo "$id2" | wc -l | tr -d ' ')" = 1 ] && check ok "exactly one container" || check bad "exactly one container"
make --no-print-directory down >/dev/null 2>&1
[ -z "$(running)" ] && check ok "make down removes it" || check bad "make down removes it"
exit $fail
