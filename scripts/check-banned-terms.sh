#!/bin/sh
# Banned-terms search over the files git tracks (and stages), with app/ left out.
#
# The terms live in .banned-terms.local (git ignores it; see .banned-terms.local.example). Set
# BANNED_TERMS_FILE to use another file. The tracked files are streamed into a labelled container as
# a tar, so the container sees a copy of what would be published and nothing else from the Mac. The
# terms file is mounted read-only. The container has no ports, no network and no credentials.
#
# It checks file contents and file names. Matching is literal and ignores case. Binary files are skipped.
# Output is only: the file, the line number and the position of the term in the list ("term #3").
# It never prints a term and never prints the matching line.
#
# Exit 0: clean. Exit 1: at least one match. Exit 2: nothing was checked (no terms file, no terms in it,
# or the container failed). A check with no terms must not look like a clean result.
set -u
cd "$(dirname "$0")/.."
PY_IMAGE=${PY_IMAGE:-$(sed -n 's/^PY_IMAGE="\(.*\)"$/\1/p' scan/python.conf)}
TERMS=${BANNED_TERMS_FILE:-.banned-terms.local}

[ -f "$TERMS" ] || { echo "check-banned-terms: FAILED: no terms file at $TERMS. Copy .banned-terms.local.example to .banned-terms.local and add the terms. Nothing was checked." >&2; exit 2; }
case "$TERMS" in /*) terms_path=$TERMS;; *) terms_path=$PWD/$TERMS;; esac

git ls-files -z -- . ':!app' | tar --null -T - -cf - 2>/dev/null | docker run -i --rm --label project=governed-remediation \
  --network none -v "$terms_path:/terms:ro" "$PY_IMAGE" sh -c '
    mkdir /w && tar -xf - -C /w
    # Clean list: no comments, no blank lines, no surrounding spaces, no carriage returns.
    tr -d "\r" < /terms | sed -e "s/^[[:space:]]*//" -e "s/[[:space:]]*$//" | grep -v -e "^#" -e "^$" > /tmp/terms
    n=$(wc -l < /tmp/terms)
    if [ "$n" -eq 0 ]; then
      echo "check-banned-terms: FAILED: the terms file holds no terms. Nothing was checked." >&2; exit 2
    fi
    files=$(find /w -type f | wc -l)
    hits=0; i=0
    while IFS= read -r term; do
      i=$((i+1))
      # Contents: file and line only. cut drops the matching text.
      grep -rIniF -e "$term" /w 2>/dev/null | cut -d: -f1,2 | sed "s|^/w/||" | while IFS=: read -r f l; do
        echo "match: $f:$l (term #$i)"; done > /tmp/m.$i
      # Names.
      find /w -type f | sed "s|^/w/||" | grep -iF -e "$term" | while IFS= read -r f; do
        echo "match: $f (file name, term #$i)"; done >> /tmp/m.$i
      cat /tmp/m.$i
      hits=$((hits + $(wc -l < /tmp/m.$i)))
    done < /tmp/terms
    if [ "$hits" -gt 0 ]; then
      echo "check-banned-terms: FOUND $hits match(es) for $n term(s) in $files tracked file(s) (app/ excluded)"; exit 1
    fi
    echo "check-banned-terms: clean. $n term(s), $files tracked file(s) (app/ excluded)"'
rc=$?
[ "$rc" -le 2 ] || { echo "check-banned-terms: FAILED: the container failed (exit $rc). Nothing was checked." >&2; exit 2; }
exit "$rc"
