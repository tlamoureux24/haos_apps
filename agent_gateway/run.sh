#!/usr/bin/with-contenv bashio
set -euo pipefail

readonly runtime_uid=1000
readonly runtime_gid=1000

install -d -m 0700 -o "${runtime_uid}" -g "${runtime_gid}" /data /data/private

if bashio::fs.file_exists /data/options.json; then
  log_level="$(bashio::config 'log_level')"
else
  log_level="${AGENT_GATEWAY_LOG_LEVEL:-info}"
fi

export AGENT_GATEWAY_DATA_DIR="${AGENT_GATEWAY_DATA_DIR:-/data}"
export AGENT_GATEWAY_LOG_LEVEL="${log_level}"
export PYTHONPATH=/app/src

bashio::log.info "Applying Agent Gateway database migrations"
su-exec agent-gateway:agent-gateway alembic -c /app/alembic.ini upgrade head

pids=()

stop_servers() {
  local pid
  for pid in "${pids[@]:-}"; do
    kill -TERM "${pid}" 2>/dev/null || true
  done
  wait || true
}
trap stop_servers TERM INT EXIT

bashio::log.info "Starting private Ingress administration listener"
su-exec agent-gateway:agent-gateway env AGENT_GATEWAY_SURFACE=admin \
  uvicorn agent_gateway.main:app --host 0.0.0.0 --port 8099 \
  --no-access-log --log-level "${log_level}" &
pids+=("$!")

bashio::log.info "Starting authenticated MCP and event listener"
su-exec agent-gateway:agent-gateway env AGENT_GATEWAY_SURFACE=public \
  uvicorn agent_gateway.main:app --host 0.0.0.0 --port 8098 \
  --no-access-log --log-level "${log_level}" &
pids+=("$!")

while true; do
  for pid in "${pids[@]}"; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      wait "${pid}" || status=$?
      bashio::log.error "Agent Gateway listener stopped unexpectedly"
      exit "${status:-1}"
    fi
  done
  sleep 1
done
