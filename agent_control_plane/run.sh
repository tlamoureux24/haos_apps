#!/usr/bin/with-contenv /bin/sh
set -eu

runtime_uid=1000
runtime_gid=1000
export PYTHONDONTWRITEBYTECODE=1

chown "${runtime_uid}:${runtime_gid}" /data
su-exec agent-control-plane:agent-control-plane install -d -m 0700 /data/private
pepper_hex="$(su-exec agent-control-plane:agent-control-plane env PYTHONPATH=/app/src python3 -c 'from pathlib import Path; from agent_control_plane.security import load_or_create_pepper; print(load_or_create_pepper(Path("/data/private/credential-pepper")).hex())')"

if [ -f /data/options.json ]; then
  log_level="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("log_level", "info"))')"
  intake_rate_limit="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("intake_rate_limit_per_minute", 30))')"
else
  log_level="${AGENT_CONTROL_PLANE_LOG_LEVEL:-info}"
  intake_rate_limit="${AGENT_CONTROL_PLANE_INTAKE_RATE_LIMIT:-30}"
fi

export AGENT_CONTROL_PLANE_DATA_DIR="${AGENT_CONTROL_PLANE_DATA_DIR:-/data}"
export AGENT_CONTROL_PLANE_LOG_LEVEL="${log_level}"
export AGENT_CONTROL_PLANE_INTAKE_RATE_LIMIT="${intake_rate_limit}"
export AGENT_CONTROL_PLANE_CREDENTIAL_PEPPER_HEX="${pepper_hex}"
export PYTHONPATH=/app/src

log_info() {
  timestamp="$(python3 -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec="seconds"))')"
  printf '%s [Agent Control Plane] INFO: %s\n' "${timestamp}" "$*"
}

log_error() {
  timestamp="$(python3 -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec="seconds"))')"
  printf '%s [Agent Control Plane] ERROR: %s\n' "${timestamp}" "$*" >&2
}

log_info "Initializing Agent Control Plane database schema"
su-exec agent-control-plane:agent-control-plane python3 -m agent_control_plane.database initialize

admin_pid=""
public_pid=""

stop_servers() {
  for pid in "${admin_pid}" "${public_pid}"; do
    if [ -n "${pid}" ]; then
      kill -TERM "${pid}" 2>/dev/null || true
    fi
  done
  wait || true
}
trap stop_servers TERM INT EXIT

log_info "Starting private Ingress administration listener"
su-exec agent-control-plane:agent-control-plane env AGENT_CONTROL_PLANE_SURFACE=admin \
  python3 -m uvicorn agent_control_plane.main:app --host 0.0.0.0 --port 8099 \
  --no-access-log --log-level "${log_level}" \
  --log-config /app/src/agent_control_plane/uvicorn_logging.json &
admin_pid=$!

log_info "Starting authenticated MCP and event listener"
su-exec agent-control-plane:agent-control-plane env AGENT_CONTROL_PLANE_SURFACE=public \
  python3 -m uvicorn agent_control_plane.main:app --host 0.0.0.0 --port 8098 \
  --no-access-log --log-level "${log_level}" \
  --log-config /app/src/agent_control_plane/uvicorn_logging.json &
public_pid=$!

while true; do
  for pid in "${admin_pid}" "${public_pid}"; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      if wait "${pid}"; then
        status=1
      else
        status=$?
      fi
      log_error "Agent Control Plane listener stopped unexpectedly"
      exit "${status}"
    fi
  done
  sleep 1
done
