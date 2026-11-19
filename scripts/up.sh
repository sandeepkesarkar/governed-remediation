#!/bin/sh
# Step "up" (spec specs/M2-thin-slice.md, section 2, step 1).
# Runs the Juice Shop image built from app/ with compose.yaml, published on 127.0.0.1 only.
# Waits for an API call to answer (not only "/"). On any failure it removes the container
# and exits non-zero. A second run replaces the old container.
#
# Settings (environment):
#   UP_TIMEOUT          seconds to wait for the health call (default 90)
#   UP_EXPECT_VERSION   version the API must report (default 20.0.0)
set -u
cd "$(dirname "$0")/.."

SERVICE=juice-shop-prod
TIMEOUT=${UP_TIMEOUT:-90}
EXPECT=${UP_EXPECT_VERSION:-20.0.0}
COMPOSE="docker compose -f compose.yaml"

fail() {
  echo "up: FAILED: $1" >&2
  $COMPOSE down --remove-orphans >/dev/null 2>&1
  exit 1
}

IMAGE=$($COMPOSE config --images 2>/dev/null | head -n 1)
docker image inspect "$IMAGE" >/dev/null 2>&1 || { echo "up: image $IMAGE not found. Run: make build-app" >&2; exit 2; }

# Replace any old container, then start.
$COMPOSE down --remove-orphans >/dev/null 2>&1
$COMPOSE up -d --no-build "$SERVICE" >/dev/null 2>&1 || fail "docker compose up"

# The port comes from compose.yaml. It must be bound to 127.0.0.1.
BINDING=$($COMPOSE port "$SERVICE" 3000 2>/dev/null | head -n 1)
HOST=${BINDING%:*}
PORT=${BINDING##*:}
[ "$HOST" = "127.0.0.1" ] || fail "port is bound to '$HOST', not 127.0.0.1"
[ -n "$PORT" ] || fail "could not read the published port"

# Wait for an API call, with a timeout.
URL="http://127.0.0.1:$PORT/rest/admin/application-version"
end=$(( $(date +%s) + TIMEOUT ))
while :; do
  body=$(curl -fsS -m 3 "$URL" 2>/dev/null) && break
  [ "$(date +%s)" -lt "$end" ] || fail "no answer from $URL within ${TIMEOUT}s"
  sleep 2
done
case "$body" in
  *"\"version\":\"$EXPECT\""*) ;;
  *) fail "unexpected version in answer (wanted $EXPECT)" ;;
esac
echo "up: ok. $SERVICE answers on 127.0.0.1:$PORT (version $EXPECT)"
