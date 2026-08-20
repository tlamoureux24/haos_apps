#!/usr/bin/with-contenv /bin/sh
set -eu

runtime_uid=1000
runtime_gid=1000
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/app/src

chown "${runtime_uid}:${runtime_gid}" /data
su-exec agent-execution-plane:agent-execution-plane install -d -m 0700 /data/private
su-exec agent-execution-plane:agent-execution-plane env PYTHONPATH=/app/src \
  python3 -c 'from pathlib import Path; from agent_execution_plane.security import load_or_create_key; load_or_create_key(Path("/data/private/provider-key"))'

if [ -f /data/options.json ]; then
  log_level="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("log_level", "info"))')"
else
  log_level="${AGENT_EXECUTION_PLANE_LOG_LEVEL:-info}"
fi
export AGENT_EXECUTION_PLANE_DATA_DIR="${AGENT_EXECUTION_PLANE_DATA_DIR:-/data}"
export AGENT_EXECUTION_PLANE_LOG_LEVEL="${log_level}"

log() {
  timestamp="$(python3 -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec="seconds"))')"
  printf '%s [Agent Execution Plane] %s: %s\n' "${timestamp}" "$1" "$2"
}

log INFO "Initializing generation-1 database schema"
su-exec agent-execution-plane:agent-execution-plane python3 -m agent_execution_plane.database initialize

admin_pid=""
api_pid=""
stop_servers() {
  log INFO "Stopping application listeners"
  for pid in "${admin_pid}" "${api_pid}"; do
    [ -z "${pid}" ] || kill -TERM "${pid}" 2>/dev/null || true
  done
  wait || true
}
trap stop_servers TERM INT EXIT

log INFO "Starting private Ingress administration listener on 8099"
su-exec agent-execution-plane:agent-execution-plane env AGENT_EXECUTION_PLANE_SURFACE=admin \
  python3 -m uvicorn agent_execution_plane.main:app --host 0.0.0.0 --port 8099 \
  --no-access-log --log-level "${log_level}" --log-config /app/src/agent_execution_plane/uvicorn_logging.json &
admin_pid=$!

log INFO "Starting standalone API listener on 8098 (health endpoints only)"
su-exec agent-execution-plane:agent-execution-plane env AGENT_EXECUTION_PLANE_SURFACE=api \
  python3 -m uvicorn agent_execution_plane.main:app --host 0.0.0.0 --port 8098 \
  --no-access-log --log-level "${log_level}" --log-config /app/src/agent_execution_plane/uvicorn_logging.json &
api_pid=$!

while true; do
  for pid in "${admin_pid}" "${api_pid}"; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      wait "${pid}" || status=$?
      log ERROR "An application listener stopped unexpectedly"
      exit "${status:-1}"
    fi
  done
  sleep 1
done
