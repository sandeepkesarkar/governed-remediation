#!/usr/bin/env bash
# S2a spike launcher. Throwaway. Runs: agent-server container (the sandbox) + client container.
# Usage: run.sh [MAX_BUDGET_USD] [MAX_ITER] [WALL_SECONDS]
set -euo pipefail
export PATH="$HOME/.rd/bin:$PATH"
cd "$(dirname "$0")"
REPO=$(cd ../.. && pwd)
SC=${SDK_DIR:?set SDK_DIR to the dir holding the pip --target install}
BUDGET=${1:-1.00}; ITER=${2:-20}; WALL=${3:-600}
MODEL=${MODEL:-anthropic/claude-sonnet-5-5}
SERVER=ghcr.io/openhands/agent-server:1.63.1-python@sha256:506c2e243dcc3f5092ad0909c5dff9fef621298faed9042b5d4b0375fac837a5
CLIENT=python:3.13.18-slim@sha256:7249d5587b78209a006dc4a3b5340678f84ea729239193aa559962cd8c1fce50
LBL=project=governed-remediation
mkdir -p out
cleanup() { docker rm -f -v s2a-agent s2a-client >/dev/null 2>&1 || true; docker network rm s2a-net >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup
docker network create --label $LBL s2a-net >/dev/null
# Sandbox: no published ports, no mounts, no env secrets. Workspace is the container's own filesystem.
docker run -d --name s2a-agent --label $LBL --network s2a-net \
  --cap-drop ALL --security-opt no-new-privileges --memory 2g --pids-limit 512 \
  "$SERVER" --host 0.0.0.0 >/dev/null
for i in $(seq 1 60); do
  docker run --rm --network s2a-net --label $LBL "$CLIENT" python -c "import urllib.request;urllib.request.urlopen('http://s2a-agent:8000/health',timeout=2)" 2>/dev/null && break
  sleep 2
done
# Seed the throwaway scratch files inside the sandbox (synthetic bug).
docker exec -i s2a-agent sh -c 'mkdir -p /workspace/scratch && cd /workspace/scratch &&
printf "def add(a, b):\n    return a - b\n" > calc.py &&
printf "from calc import add\nassert add(2, 3) == 5\nprint(\"ok\")\n" > test_calc.py'
# Key: taken from .env into this shell only; passed by name so it never appears on a command line.
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' "$REPO/.env" | cut -d= -f2-)
# Client: sees only the SDK (read-only) and the client script (read-only) and an output dir. No repo, no home.
timeout "$WALL" docker run --name s2a-client --label $LBL --network s2a-net \
  -e ANTHROPIC_API_KEY -e AGENT_HOST=http://s2a-agent:8000 -e MODEL="$MODEL" \
  -e MAX_BUDGET="$BUDGET" -e MAX_ITER="$ITER" -e PYTHONPATH=/sdk \
  -v "$SC":/sdk:ro -v "$PWD/client":/client:ro -v "$PWD/out":/out \
  "$CLIENT" python /client/run.py 2>&1 | tee out/client.log | grep -v -i 'api_key' || echo "WALL-CLOCK OR CLIENT FAILURE: exit $?"
docker exec s2a-agent sh -c 'cd /workspace/scratch && cat calc.py test_calc.py && python test_calc.py' > out/final-files.txt 2>&1 || true
echo "--- final scratch files"; cat out/final-files.txt
