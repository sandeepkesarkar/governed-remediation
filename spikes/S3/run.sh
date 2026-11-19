#!/usr/bin/env bash
# Spike S3 helper. Runs one compose service as a named one-shot container, and records
# wall time and peak memory (sampled about once a second with docker stats).
# usage: run.sh <short-name> <service> [command args...]
# Results append to spikes/S3/results.log (small, kept in git).
set -u
cd "$(dirname "$0")"
name=$1; svc=$2; shift 2
ctr="s3-$name"
tmp=$(mktemp)
sampler() {
  while :; do
    docker stats --no-stream --format '{{.MemUsage}}' "$ctr" 2>/dev/null | awk '{
      v=$1; u=v; gsub(/[0-9.]/,"",u); n=v; gsub(/[A-Za-z]/,"",n);
      if (u=="GiB") n*=1024; else if (u=="KiB") n/=1024; else if (u=="B") n/=1048576;
      printf "%.1f\n", n }' >> "$tmp"
    sleep 0.5
  done
}
sampler & spid=$!
start=$(python3 -c 'import time;print(time.time())')
docker compose -f compose.yaml --profile tools --profile target run --rm --name "$ctr" "$svc" "$@"
rc=$?
end=$(python3 -c 'import time;print(time.time())')
kill $spid 2>/dev/null; wait $spid 2>/dev/null
peak=$(sort -n "$tmp" | tail -1); samples=$(wc -l < "$tmp" | tr -d ' '); rm -f "$tmp"
printf '%s svc=%s exit=%s seconds=%.1f peak_mem_mib=%s samples=%s\n' "$name" "$svc" "$rc" "$(python3 -c "print($end-$start)")" "${peak:-n/a}" "$samples" | tee -a results.log
exit $rc
