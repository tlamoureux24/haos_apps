#!/usr/bin/with-contenv /bin/sh
set -eu

runtime_uid=1000
runtime_gid=1000

chown "${runtime_uid}:${runtime_gid}" /data
if [ -d /data/private ]; then
  chown "${runtime_uid}:${runtime_gid}" /data/private
  chmod 0700 /data/private
else
  su-exec agent-gateway:agent-gateway mkdir -m 0700 /data/private
fi

if [ -f /data/options.json ]; then
  log_level="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("log_level", "info"))')"
else
  log_level="${AGENT_GATEWAY_LOG_LEVEL:-info}"
fi

export AGENT_GATEWAY_DATA_DIR="${AGENT_GATEWAY_DATA_DIR:-/data}"
export AGENT_GATEWAY_LOG_LEVEL="${log_level}"
export PYTHONPATH=/app/src

log_info() {
  printf '[Agent Gateway] INFO: %s\n' "$*"
}

log_error() {
  printf '[Agent Gateway] ERROR: %s\n' "$*" >&2
}

log_info "Applying Agent Gateway database migrations"
su-exec agent-gateway:agent-gateway alembic -c /app/alembic.ini upgrade head

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
su-exec agent-gateway:agent-gateway env AGENT_GATEWAY_SURFACE=admin \
  uvicorn agent_gateway.main:app --host 0.0.0.0 --port 8099 \
  --no-access-log --log-level "${log_level}" &
admin_pid=$!

log_info "Starting authenticated MCP and event listener"
su-exec agent-gateway:agent-gateway env AGENT_GATEWAY_SURFACE=public \
  uvicorn agent_gateway.main:app --host 0.0.0.0 --port 8098 \
  --no-access-log --log-level "${log_level}" &
public_pid=$!

while true; do
  for pid in "${admin_pid}" "${public_pid}"; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      if wait "${pid}"; then
        status=1
      else
        status=$?
      fi
      log_error "Agent Gateway listener stopped unexpectedly"
      exit "${status}"
    fi
  done
  sleep 1
done
