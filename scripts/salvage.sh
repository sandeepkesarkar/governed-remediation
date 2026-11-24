# Sourced by scripts/fix.sh and tests/isolation-test.sh. It defines a function and does nothing when loaded.

# salvage_output SANDBOX DEST
# Copies the sandbox's working copy (without node_modules) out as a tar file at DEST. The tar is only data: it is
# never unpacked on the Mac. Writes to DEST.part first, so a half-written file is never left under the real name.
# Returns 0 if a non-empty tar was saved, 1 otherwise (the sandbox is gone, or the copy failed). It never exits
# the calling script and never prints a variable value.
salvage_output() {
  docker inspect "$1" >/dev/null 2>&1 || return 1
  mkdir -p "$(dirname "$2")" || return 1
  if docker exec "$1" tar -C /workspace/app --exclude=./node_modules -cf - . > "$2.part" 2>/dev/null && [ -s "$2.part" ]; then
    mv -f "$2.part" "$2"
    return 0
  fi
  rm -f "$2.part"
  return 1
}
