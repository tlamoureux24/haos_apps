#!/bin/bash
# Container smoke test for Claude Remote, shared by the validate and update
# workflows. Usage: smoke_test.sh IMAGE  (CONTAINER=podman to run locally)
# APPARMOR=1 loads apparmor.txt on the host (sudo) and runs every App
# container under it, then checks the claude and claude_shell sub-profiles.
set -euo pipefail

image="$1"
engine="${CONTAINER:-docker}"
run_id="claude-remote-smoke-$$"
root="$(mktemp -d)"
network="${run_id}"
secret="private_ci-secret-$$"
app_dir="$(cd "$(dirname "$0")/.." && pwd)"
security_opts=()
if [[ "${APPARMOR:-}" == "1" ]]; then
  sudo apparmor_parser --replace --write-cache "${app_dir}/apparmor.txt"
  security_opts=(--security-opt apparmor=claude_remote)
fi

passed=false
cleanup() {
  for name in "${run_id}" "${run_id}-empty" "${run_id}-invalid" "${run_id}-mcp" "${run_id}-probe" "${run_id}-aa"; do
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
  shift 2
  mkdir -p "${root}/${name}"
  jq -n --arg url "${url}" '{log_level: "info", ha_mcp_url: $url, confirm_writes: true}' \
    >"${root}/${name}/options.json"
  "${engine}" run --detach --name "${name}" --network "${network}" "${security_opts[@]}" \
    --env SUPERVISOR_TOKEN=ci-supervisor-token --env HASS_TOKEN=ci-hass-token \
    --env TZ=Europe/Paris \
    --volume "${root}/${name}:/data:Z" "$@" "${image}" >/dev/null
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

# --- AppArmor: enforced profile and the two sub-profiles ----------------------
if [[ "${APPARMOR:-}" == "1" ]]; then
  label="$(app_exec "${run_id}" cat /proc/1/attr/current)"
  [[ "${label}" == "claude_remote (enforce)" ]] || fail "App not confined by claude_remote: ${label}"

  # A stand-in claude binary: it runs in claude_remote//claude like the real
  # one, then starts ordinary programs, which must land in claude_shell.
  cat >"${root}/claude-probe" <<'PROBE'
#!/bin/bash
# Only answers "probe"; "nested" proves that a program could start Claude.
case "${1:-}" in
  nested) echo nested-ran; exit 0 ;;
  probe) ;;
  *) exit 1 ;;
esac
read -r own </proc/self/attr/current
echo "claude=${own}"
echo "shell=$(cat /proc/self/attr/current)"
echo probe >/data/home/.claude-probe && echo "claude_home_write=ok"
/usr/local/bin/claude-remote-setup </dev/null >/dev/null 2>&1 && echo "claude_exec_app=open" || echo "claude_exec_app=blocked"
curl --silent --max-time 3 --output /dev/null http://ha-mcp:9583/ && echo "shell_network=open" || echo "shell_network=blocked"
cat /etc/claude-code/managed-mcp.json >/dev/null 2>&1 && echo "shell_mcp_url=readable" || echo "shell_mcp_url=blocked"
cat /data/home/.claude/.credentials.json >/dev/null 2>&1 && echo "shell_credentials=readable" || echo "shell_credentials=blocked"
touch /data/home/.bashrc 2>/dev/null && echo "shell_home_write=open" || echo "shell_home_write=blocked"
touch /data/workspace/.probe 2>/dev/null && echo "shell_workspace_write=ok" || echo "shell_workspace_write=blocked"
[[ "$(sh -c '/usr/local/bin/claude nested' 2>/dev/null)" == nested-ran ]] && echo "shell_exec_claude=open" || echo "shell_exec_claude=blocked"
PROBE
  chmod 0755 "${root}/claude-probe"
  start_app "${run_id}-aa" "http://ha-mcp:9583/${secret}" --volume "${root}/claude-probe:/usr/local/bin/claude:ro"
  wait_healthy "${run_id}-aa"
  app_exec "${run_id}-aa" sh -c 'install -d -o claude -g claude -m 0700 /data/home/.claude && echo "{}" >/data/home/.claude/.credentials.json && chown claude:claude /data/home/.claude/.credentials.json'
  probe="$(app_exec --user claude --env HOME=/data/home --workdir /data/workspace "${run_id}-aa" /usr/local/bin/claude probe 2>&1)"
  echo "${probe}"
  for expected in \
      "claude=claude_remote//claude (enforce)" \
      "shell=claude_remote//claude_shell (enforce)" \
      "claude_home_write=ok" \
      "claude_exec_app=blocked" \
      "shell_network=blocked" \
      "shell_mcp_url=blocked" \
      "shell_credentials=blocked" \
      "shell_home_write=blocked" \
      "shell_workspace_write=ok" \
      "shell_exec_claude=blocked"; do
    grep -qxF "${expected}" <<<"${probe}" || fail "AppArmor probe: expected ${expected}"
  done
fi

passed=true
echo "Claude Remote smoke test passed"
