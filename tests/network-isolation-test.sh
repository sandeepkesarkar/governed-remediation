#!/bin/sh
# Proves "exploit-net" (compose.yaml) has no route out, not just that the YAML says
# internal: true. A throwaway container with only that network must fail to reach an
# external host. Run after "make up" (the network must exist); needs no app code.
# A public IP is used, not a name, so a failed DNS lookup (also expected: the network
# has no DNS either) cannot be mistaken for success.
set -u
cd "$(dirname "$0")/.."
NETWORK=governed-remediation_exploit-net
EXTERNAL_IP=1.1.1.1    # a public DNS server. Only used as a plain, nameless target.
PY_IMAGE=$(sed -n 's/^PY_IMAGE="\(.*\)"$/\1/p' scan/python.conf)

fail=0
check() { if [ "$1" = ok ]; then echo "PASS: $2"; else echo "FAIL: $2"; fail=1; fi; }

docker network inspect "$NETWORK" >/dev/null 2>&1 || { echo "FAIL: network $NETWORK not found. Run: make up"; exit 1; }

docker run --rm --label project=governed-remediation --network "$NETWORK" --network-alias isolation-probe \
  "$PY_IMAGE" python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(('$EXTERNAL_IP', 443))
    sys.exit(1)        # connected: isolation failed
except OSError:
    sys.exit(0)         # refused, unreachable or timed out: isolation holds
" >/dev/null 2>&1
rc=$?
[ "$rc" -eq 0 ] && check ok "a container with only $NETWORK cannot reach $EXTERNAL_IP (no route out)" \
  || check bad "a container with only $NETWORK cannot reach $EXTERNAL_IP (got exit $rc, expected a connection failure)"

exit $fail
