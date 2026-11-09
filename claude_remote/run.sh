#!/usr/bin/with-contenv bash
# Claude Remote App entrypoint (runs as root under the HA base s6 init).
# Prepares the unprivileged claude user, writes the Claude Code policy for the
# HA-MCP server, then supervises the Ingress page, the admin terminal and the
# Remote Control loop.
set -euo pipefail

readonly OPTIONS="/data/options.json"
readonly DATA_HOME="/data/home"
readonly WORKSPACE="/data/workspace"
readonly MANAGED_DIR="/etc/claude-code"
readonly UI="/usr/local/lib/claude-remote/ingress_ui.py"
readonly READ_TOOLS=(
  "mcp__home-assistant__ha_get_*"
  "mcp__home-assistant__ha_list_*"
  "mcp__home-assistant__ha_search*"
  "mcp__home-assistant__ha_config_get_*"
  "mcp__home-assistant__ha_config_list_*"
  "mcp__home-assistant__ha_eval_template"
)

log() {
  local level="$1"
  shift
  printf '%s [Claude Remote] %s: %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z | sed 's/\([0-9][0-9]\)$/:\1/')" "${level}" "$*" >&2
}
event() { python3 "${UI}" event "$@" || log WARNING "Could not record activity event $1"; }
state() { python3 "${UI}" status "$@" || log WARNING "Could not update status"; }

option() { jq -r --arg key "$1" '.[$key] // empty' "${OPTIONS}"; }

# --- Persistent layout --------------------------------------------------------
mkdir -p "${DATA_HOME}/.claude" "${WORKSPACE}" /run/nginx "${MANAGED_DIR}/managed-settings.d"
chmod 0700 "${DATA_HOME}" "${DATA_HOME}/.claude"
chown -R claude:claude "${DATA_HOME}" "${WORKSPACE}"

log INFO "Starting Claude Remote ${BUILD_VERSION:-dev}"
event app_started --status ok "version=${BUILD_VERSION:-dev}"
claude_version="$(s6-setuidgid claude env -i HOME="${DATA_HOME}" PATH=/usr/local/bin:/usr/bin:/bin \
  /usr/local/bin/claude --version 2>/dev/null | awk '{print $1}')"
state "claude_version=${claude_version:-unknown}" remote_control=starting mcp_reachable=unknown

# --- HA-MCP server: the only MCP server Claude can use -----------------------
ha_mcp_url="$(option ha_mcp_url)"
rm -f "${MANAGED_DIR}/managed-mcp.json"
if [[ -z "${ha_mcp_url}" ]]; then
  # An empty managed MCP file still gives the App exclusive control: no other
  # server can be added from the terminal or the phone.
  jq -n '{mcpServers: {}}' >"${MANAGED_DIR}/managed-mcp.json"
  log WARNING "No HA-MCP URL configured: Claude has no access to Home Assistant"
  event mcp_not_configured --status warning
  state mcp=not_configured
elif [[ ! "${ha_mcp_url}" =~ ^https?://[^[:space:]]+/private_[^/[:space:]]+$ ]]; then
  log ERROR "ha_mcp_url must be the HTTP(S) URL shown by the HA-MCP App, ending in /private_<secret>"
  event mcp_not_configured --status error
  exit 1
else
  jq -n --arg url "${ha_mcp_url}" \
    '{mcpServers: {"home-assistant": {type: "http", url: $url}}}' \
    >"${MANAGED_DIR}/managed-mcp.json"
  log INFO "Configured the private HA-MCP server (URL not logged)"
  event mcp_configured --status ok
  state mcp=configured
  http_status="$(curl --silent --output /dev/null --write-out '%{http_code}' --max-time 5 \
    --header 'Content-Type: application/json' \
    --header 'Accept: application/json, text/event-stream' \
    --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"claude-remote-check","version":"1"}}}' \
    "${ha_mcp_url}" || true)"
  if [[ "${http_status}" =~ ^2[0-9][0-9]$ ]]; then
    log INFO "HA-MCP server reachable (HTTP ${http_status})"
    event mcp_reachable --status ok "http_status=${http_status}"
    state mcp_reachable=true
  else
    log WARNING "HA-MCP server not reachable (HTTP ${http_status:-000}); check the URL and that the HA-MCP App is started"
    event mcp_unreachable --status warning "http_status=${http_status:-000}"
    state mcp_reachable=false
  fi
fi
chown root:claude "${MANAGED_DIR}/managed-mcp.json"
chmod 0640 "${MANAGED_DIR}/managed-mcp.json"
unset ha_mcp_url

# Read tools run without confirmation; anything else asks on the phone unless
# confirm_writes is false. HA-MCP's own read-only mode stays the real boundary.
if [[ "$(option confirm_writes)" == "false" ]]; then
  allow_json='["mcp__home-assistant__*"]'
  log INFO "Every HA-MCP tool runs without confirmation (confirm_writes: false)"
else
  allow_json="$(printf '%s\n' "${READ_TOOLS[@]}" | jq -R . | jq -s .)"
  log INFO "HA-MCP read tools run directly; other tools ask for confirmation"
fi
jq -n --argjson allow "${allow_json}" '{permissions: {allow: $allow}}' \
  >"${MANAGED_DIR}/managed-settings.d/50-ha-mcp.json"
chmod 0644 "${MANAGED_DIR}/managed-settings.d/50-ha-mcp.json"

# --- Services -----------------------------------------------------------------
pids=()
stopping=false
shutdown() {
  stopping=true
  log INFO "Stopping Claude Remote"
  event app_stopping --status info
  kill "${pids[@]}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap shutdown TERM INT

python3 "${UI}" serve --port 8100 &
pids+=("$!")

s6-setuidgid claude env -i \
  HOME="${DATA_HOME}" USER=claude LOGNAME=claude SHELL=/bin/bash \
  PATH=/usr/local/bin:/usr/bin:/bin TERM=xterm-256color LANG=C.UTF-8 \
  TZ="${TZ:-}" \
  ttyd --interface 127.0.0.1 --port 7681 --writable \
    --client-option titleFixed="Claude Remote" \
    /usr/local/bin/claude-shell &
pids+=("$!")

nginx -c /etc/claude-remote/nginx.conf -g 'daemon off;' &
pids+=("$!")

/usr/local/bin/claude-remote-control &
pids+=("$!")

log INFO "Ingress page and admin terminal ready; run 'claude-remote-setup' once in the terminal"

set +e
wait -n "${pids[@]}"
code=$?
set -e
if [[ "${stopping}" == "false" ]]; then
  log ERROR "A Claude Remote service exited (code ${code}); stopping the App"
  kill "${pids[@]}" 2>/dev/null || true
  exit 1
fi
