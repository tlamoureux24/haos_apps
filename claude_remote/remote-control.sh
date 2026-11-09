#!/bin/bash
# Keeps `claude remote-control` running as the unprivileged claude user once
# the account is signed in and the one-time setup has been accepted.
set -uo pipefail

readonly DATA_HOME="/data/home"
readonly WORKSPACE="/data/workspace"
readonly SETUP_MARKER="${DATA_HOME}/.claude-remote/setup-done"
readonly UI="/usr/local/lib/claude-remote/ingress_ui.py"
readonly SESSION_NAME="Home Assistant"
readonly POLL_S=20
readonly MIN_DELAY_S=10
readonly MAX_DELAY_S=300
# A run shorter than this counts as a failed start for the backoff.
readonly HEALTHY_RUN_S=120

log() {
  local level="$1"
  shift
  printf '%s [Claude Remote] %s: %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z | sed 's/\([0-9][0-9]\)$/:\1/')" "${level}" "$*" >&2
}
event() { python3 "${UI}" event "$@" || log WARNING "Could not record activity event $1"; }
state() { python3 "${UI}" status "$@" || log WARNING "Could not update status"; }

# Clean environment for every Claude process: no Supervisor credentials and
# none of the variables that would replace the claude.ai login.
as_claude() {
  s6-setuidgid claude env -i \
    HOME="${DATA_HOME}" USER=claude LOGNAME=claude SHELL=/bin/bash \
    PATH=/usr/local/bin:/usr/bin:/bin TERM=xterm-256color LANG=C.UTF-8 \
    TZ="${TZ:-}" \
    "$@"
}

# Strip terminal control sequences, drop blank and repeated lines, timestamp.
relay_output() {
  local line previous=""
  while IFS= read -r line; do
    line="$(printf '%s' "${line}" | sed -E $'s/\x1b\\[[0-9;?]*[ -/]*[@-~]//g; s/\x1b\\][^\x07]*(\x07|\x1b\\\\)//g; s/\r//g; s/[[:cntrl:]]//g')"
    [[ -z "${line//[[:space:]]/}" || "${line}" == "${previous}" ]] && continue
    previous="${line}"
    log INFO "remote-control: ${line}"
  done
}

logged_in=unknown
setup_reported=false
delay="${MIN_DELAY_S}"

while true; do
  # Remote Control only works with a claude.ai subscription login.
  if ! as_claude claude auth status 2>/dev/null \
      | jq -e '.loggedIn == true and .authMethod == "claude.ai"' >/dev/null 2>&1; then
    if [[ "${logged_in}" != "false" ]]; then
      log WARNING "No claude.ai subscription sign-in: open the App, then the terminal, and run claude-remote-setup"
      event login_required --status warning
      state logged_in=false remote_control=waiting_login
      logged_in=false
    fi
    sleep "${POLL_S}"
    continue
  fi
  if [[ "${logged_in}" != "true" ]]; then
    log INFO "Claude account signed in"
    event login_detected --status ok
    state logged_in=true
    logged_in=true
  fi

  if [[ ! -f "${SETUP_MARKER}" ]]; then
    if [[ "${setup_reported}" == "false" ]]; then
      log WARNING "Remote Control not set up yet: run claude-remote-setup once in the terminal"
      event setup_required --status warning
      state remote_control=waiting_setup
      setup_reported=true
    fi
    sleep "${POLL_S}"
    continue
  fi
  if [[ "${setup_reported}" == "true" ]]; then
    log INFO "Remote Control setup completed"
    event setup_completed --status ok
    setup_reported=false
  fi

  log INFO "Starting Remote Control (environment \"${SESSION_NAME}\")"
  event remote_control_started --status ok
  state remote_control=running
  started=$(date +%s)
  # remote-control expects a terminal: `script` provides a pseudo-terminal and
  # the never-ending `sleep` keeps its input open without sending anything.
  exec {idle_input}< <(sleep infinity)
  idle_pid=$!
  as_claude script --quiet --flush --return \
    --command "cd ${WORKSPACE} && exec claude remote-control --name '${SESSION_NAME}' --permission-mode default" \
    /dev/null <&"${idle_input}" 2>&1 | relay_output
  code="${PIPESTATUS[0]}"
  kill "${idle_pid}" 2>/dev/null
  exec {idle_input}<&-
  ran=$(( $(date +%s) - started ))

  log WARNING "Remote Control exited with code ${code} after ${ran}s"
  event remote_control_exited --status warning "exit_code=${code}"
  if (( ran >= HEALTHY_RUN_S )); then
    delay="${MIN_DELAY_S}"
  fi
  log INFO "Restarting Remote Control in ${delay}s"
  event remote_control_restart_scheduled --status info "delay_s=${delay}"
  state remote_control=restarting
  sleep "${delay}"
  delay=$(( delay * 2 > MAX_DELAY_S ? MAX_DELAY_S : delay * 2 ))
  # The next iteration re-checks the login: a sign-out or an expired login
  # sends the loop back to waiting for sign-in.
done
