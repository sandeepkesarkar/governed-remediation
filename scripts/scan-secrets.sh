#!/bin/sh
# Secrets scan over the files git tracks (and stages), with gitleaks in a labelled container.
# The tracked files are streamed into the container as a tar, so the container sees a copy of
# exactly what would be published and nothing else from the Mac. It has no ports and
# no credentials. Settings and the path allowlist are in .gitleaks.toml. Output is redacted.
# Exit 0 means clean. Exit 1 means findings, printed as rule, file and line only.
set -u
cd "$(dirname "$0")/.."
. scan/secrets.conf

git ls-files -z | tar --null -T - -cf - 2>/dev/null | docker run -i --rm --label project=governed-remediation \
  --entrypoint sh "$GITLEAKS_IMAGE" -c '
    mkdir /w && tar -xf - -C /w
    gitleaks dir /w --config /w/.gitleaks.toml --no-banner --redact \
      --report-format json --report-path /tmp/r.json >/tmp/o.txt 2>&1
    rc=$?
    if [ $rc -eq 0 ]; then echo "scan-secrets: clean (apart from the path allowlist in .gitleaks.toml)"; exit 0; fi
    if [ $rc -ne 1 ]; then cat /tmp/o.txt; echo "scan-secrets: the scanner failed (exit $rc)"; exit 2; fi
    echo "scan-secrets: FINDINGS (count, rule, file):"
    tr "{" "\n" < /tmp/r.json | grep -o "\"RuleID\": *\"[^\"]*\"\|\"File\": *\"[^\"]*\"" | paste - - \
      | sed "s|/w/||" | awk "{print \$2, \$4}" | tr -d "\"," | sort | uniq -c | sort -k3
    exit 1'
