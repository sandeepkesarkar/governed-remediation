#!/bin/sh
# Proves the app is reachable on loopback and not on the Mac's LAN address.
# Run after "make up".
set -u
cd "$(dirname "$0")/.."
PORT=$(docker compose -f compose.yaml port juice-shop-prod 3000 2>/dev/null | head -n 1 | sed 's/.*://')
[ -n "$PORT" ] || { echo "FAIL: the app is not running. Run: make up"; exit 1; }
echo "docker port:"; docker port gr-juice-shop || exit 1
[ "$(docker port gr-juice-shop 3000/tcp | sort -u)" = "127.0.0.1:$PORT" ] || { echo "FAIL: not bound to 127.0.0.1 only"; exit 1; }
curl -fsS -m 5 "http://127.0.0.1:$PORT/rest/admin/application-version" >/dev/null || { echo "FAIL: no answer on loopback"; exit 1; }
echo "loopback: answers"
found=0
for ifc in en0 en1 en2; do
  ip=$(ipconfig getifaddr $ifc 2>/dev/null) || continue
  [ -n "$ip" ] || continue
  found=1
  if curl -s -m 5 -o /dev/null "http://$ip:$PORT/"; then
    echo "FAIL: $ip:$PORT answered. The app is reachable from the LAN address."; exit 1
  fi
  echo "LAN address $ip ($ifc): no answer. Good."
done
[ "$found" = 1 ] || { echo "No LAN address found. LAN check not done."; exit 3; }
echo "loopback check: PASS"
