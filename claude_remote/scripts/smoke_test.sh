#!/bin/bash
# Container smoke test for Claude Remote, shared by the validate and update
# workflows. Usage: smoke_test.sh IMAGE  (CONTAINER=podman to run locally)
set -euo pipefail

image="$1"
engine="${CONTAINER:-docker}"
run_id="claude-remote-smoke-$$"
root="$(mktemp -d)"
network="${run_id}"
secret="private_ci-secret-$$"

passed=false
cleanup() {
  for name in "${run_id}" "${run_id}-empty" "${run_id}-invalid" "${run_id}-mcp" "${run_id}-probe"; do
    if [[ "${passed}" == "false" && "${name}" == "${run_id}" ]]; then "${engine}" logs "${name}" 2>&1 | tail -40 || true; fi
    "${engine}" rm --force "${name}" >/dev/null 2>&1 || true
  done
  "${engine}" network rm "${network}" >/dev/null 2>&1 || true
  rm -rf "${root}" 2>/dev/null || true
}
trap cleanup EXIT

fail() { echo "SMOKE FAILURE: $*" >&2; exit 1; }
app_exec() { "${engine}" exec "$@"; }

start_app() {
  local name="$1" url="$2"
  mkdir -p "${root}/${name}"
  jq -n --arg url "${url}" '{log_level: "info", ha_mcp_url: $url, confirm_writes: true}' \
    >"${root}/${name}/options.json"
  "${engine}" run --detach --name "${name}" --network "${network}" \
    --env SUPERVISOR_TOKEN=ci-supervisor-token --env HASS_TOKEN=ci-hass-token \
    --env TZ=Europe/Paris \
    --volume "${root}/${name}:/data:Z" "${image}" >/dev/null
}

wait_healthy() {
  local name="$1"
  for _ in {1..60}; do
    if app_exec "${name}" curl --fail --silent http://127.0.0.1:8099/healthz >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "${name} did not become healthy"
}

"${engine}" network create "${network}" >/dev/null

# A stand-in HA-MCP endpoint that accepts the initialize POST.
"${engine}" run --detach --name "${run_id}-mcp" --network "${network}" --network-alias ha-mcp \
  python:3.14-alpine python -c '
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = b"{\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{}}"
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
HTTPServer(("0.0.0.0", 9583), H).serve_forever()' >/dev/null

# --- Configured URL ------------------------------------------------------------
start_app "${run_id}" "http://ha-mcp:9583/${secret}"
wait_healthy "${run_id}"
sleep 3

status="$(app_exec "${run_id}" curl --silent http://127.0.0.1:8099/api/status)"
echo "status: ${status}"
jq -e '.mcp == "configured" and .mcp_reachable == "true" and .logged_in == "false"
       and .remote_control == "waiting_login" and (.claude_version | test("^[0-9]+\\.[0-9]+\\.[0-9]+$"))' \
  <<<"${status}" >/dev/null || fail "unexpected status"

events="$(app_exec "${run_id}" curl --silent 'http://127.0.0.1:8099/api/activity' | jq -r '[.entries[].event] | join(" ")')"
echo "events: ${events}"
for code in app_started mcp_configured mcp_reachable login_required; do
  [[ " ${events} " == *" ${code} "* ]] || fail "missing activity event ${code}"
done

app_exec "${run_id}" curl --fail --silent --output /dev/null http://127.0.0.1:8099/ || fail "status page"
app_exec "${run_id}" curl --fail --silent --output /dev/null http://127.0.0.1:8099/terminal/ || fail "terminal page"

# Only the Home Assistant Ingress proxy may reach the Ingress port.
app_ip="$("${engine}" inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${run_id}")"
probe_code="$("${engine}" run --rm --name "${run_id}-probe" --network "${network}" python:3.14-alpine \
  python -c "import urllib.request,urllib.error,sys
try: print(urllib.request.urlopen('http://${app_ip}:8099/', timeout=5).status)
except urllib.error.HTTPError as e: print(e.code)")"
[[ "${probe_code}" == "403" ]] || fail "Ingress port answered ${probe_code} to a non-Ingress client"

# Claude Code: pinned binary, exclusive managed MCP, policy files.
app_exec --user claude --env HOME=/data/home "${run_id}" claude --version
add_output="$(app_exec --user claude --env HOME=/data/home --workdir /data/workspace "${run_id}" \
  claude mcp add --transport http other http://example.invalid/mcp 2>&1 || true)"
[[ "${add_output}" == *"exclusive control"* ]] || fail "another MCP server could be added: ${add_output}"
app_exec "${run_id}" sh -c '
  set -e
  test "$(stat -c "%a %U %G" /etc/claude-code/managed-mcp.json)" = "640 root claude"
  jq -e ".mcpServers | keys == [\"home-assistant\"]" /etc/claude-code/managed-mcp.json >/dev/null
  jq -e ".permissions.allow | index(\"mcp__home-assistant__ha_get_*\")" /etc/claude-code/managed-settings.d/50-ha-mcp.json >/dev/null
  jq -e ".permissions.allow | index(\"mcp__home-assistant__*\") | not" /etc/claude-code/managed-settings.d/50-ha-mcp.json >/dev/null
  test "$(stat -c %U /etc/claude-code/managed-settings.json)" = root
  ! su claude -s /bin/sh -c "test -w /etc/claude-code/managed-settings.json"
' || fail "managed policy files"

# Services run unprivileged where they touch user input, without HA credentials.
app_exec --user claude "${run_id}" sh -c '
  set -e
  pid="$(pgrep -x ttyd)"
  test "$(stat -c %u /proc/${pid})" = 1000
  ! tr "\0" "\n" </proc/${pid}/environ | grep -Eq "^(SUPERVISOR_TOKEN|HASS_TOKEN)="
' || fail "terminal process privileges or environment"

if "${engine}" logs "${run_id}" 2>&1 | grep -q "${secret}"; then
  fail "the HA-MCP secret appeared in the App log"
fi
if app_exec "${run_id}" sh -c "cat /data/activity.jsonl /data/status.json" | grep -q "${secret}"; then
  fail "the HA-MCP secret appeared in the activity journal or status"
fi

# --- No URL: Claude gets no MCP server at all ---------------------------------
start_app "${run_id}-empty" ""
wait_healthy "${run_id}-empty"
sleep 2
app_exec "${run_id}-empty" curl --silent http://127.0.0.1:8099/api/status | jq -e '.mcp == "not_configured"' >/dev/null \
  || fail "empty URL status"
app_exec "${run_id}-empty" jq -e '.mcpServers == {}' /etc/claude-code/managed-mcp.json >/dev/null \
  || fail "empty URL must still write an exclusive, empty MCP configuration"

# --- Invalid URL: the App refuses to start ------------------------------------
start_app "${run_id}-invalid" "http://ha-mcp:9583/not-private"
for _ in {1..30}; do
  running="$("${engine}" inspect --format '{{.State.Running}}' "${run_id}-invalid")"
  [[ "${running}" == "false" ]] && break
  sleep 1
done
[[ "${running}" == "false" ]] || fail "an invalid HA-MCP URL did not stop the App"

passed=true
echo "Claude Remote smoke test passed"
