# Sourced by scripts/fix.sh and tests/isolation-test.sh. It defines functions and does nothing when loaded.

# One variable from the environment, else from .env. The value goes into a variable, never to the terminal.
env_value() {
  eval "v=\${$1:-}"
  if [ -z "$v" ] && [ -f .env ]; then v=$(sed -n "s/^$1=//p" .env | head -n 1 | tr -d "\"'\r"); fi
  printf '%s' "$v"
}

# isolation_check NAME [ALLOWED_NAME ...]
# Prints the reason and returns 1 if the container:
#   - has an environment variable whose name looks like a credential (AWS, GITHUB, TOKEN, SECRET, KEY,
#     PASSWORD, ANTHROPIC, CREDENTIAL), unless that exact name is in the allowed list
#   - has the value of GITHUB_TOKEN, GITHUB_FIX_TOKEN or ANTHROPIC_API_KEY anywhere in its configuration
#     (a name in the allowed list is exempt from the value check too)
#   - has a mount that is not in ISOLATION_MOUNTS, is privileged, publishes a port, or lacks the project label
# ISOLATION_MOUNTS is a space-separated list of DESTINATION:MODE pairs, for example "/repo/agents:ro /out:rw",
# set for one call (ISOLATION_MOUNTS="..." isolation_check NAME). A mount passes only if its destination AND its
# mode both match a pair exactly. The list is a ceiling, not a requirement. With no list, any mount fails.
# Prints nothing and returns 0 if it is fine. Names are matched whole, so an allowance is for one name only.
# It prints variable names, never values.
isolation_check() {
  _name=$1; shift
  _bad=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$_name" | cut -d= -f1 \
        | grep -i -E 'AWS|GITHUB|TOKEN|SECRET|KEY|PASSWORD|ANTHROPIC|CREDENTIAL' || true)
  for _ok in "$@"; do _bad=$(printf '%s\n' "$_bad" | grep -v -x "$_ok" || true); done
  if [ -n "$(printf '%s' "$_bad" | tr -d '[:space:]')" ]; then
    echo "$_name holds credential-like variables: $(echo $_bad)"; return 1
  fi
  mkdir -p out; _tmp="out/.inspect.$$"
  docker inspect "$_name" > "$_tmp"
  for _var in GITHUB_TOKEN GITHUB_FIX_TOKEN ANTHROPIC_API_KEY; do
    case " $* " in *" $_var "*) continue;; esac
    _val=$(env_value "$_var")
    if [ -n "$_val" ] && printf '%s\n' "$_val" | grep -qF -f - "$_tmp"; then
      rm -f "$_tmp"; echo "the value of $_var appears in the configuration of $_name"; return 1
    fi
  done
  rm -f "$_tmp"
  for _m in $(docker inspect -f '{{range .Mounts}}{{.Destination}}:{{if .RW}}rw{{else}}ro{{end}}{{println}}{{end}}' "$_name"); do
    case " ${ISOLATION_MOUNTS:-} " in
      *" $_m "*) ;;
      *) echo "$_name has an unexpected mount ($_m)"; return 1;;
    esac
  done
  [ "$(docker inspect -f '{{.HostConfig.Privileged}}' "$_name")" = false ] || { echo "$_name is privileged"; return 1; }
  [ "$(docker inspect -f '{{index .Config.Labels "project"}}' "$_name")" = governed-remediation ] \
    || { echo "$_name has no project label"; return 1; }
  _ports=$(docker inspect -f '{{range $p, $b := .NetworkSettings.Ports}}{{if $b}}{{$p}} {{end}}{{end}}' "$_name")
  [ -z "$_ports" ] || { echo "$_name publishes ports: $_ports"; return 1; }
  return 0
}
