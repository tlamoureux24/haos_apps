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
  events_transport="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("events_transport", "http"))')"
  mcp_transport="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("mcp_transport", "https"))')"
  certificate_source="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("certificate_source", "self_generated"))')"
  certfile="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("certfile", ""))')"
  keyfile="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("keyfile", ""))')"
else
  log_level="${AGENT_CONTROL_PLANE_LOG_LEVEL:-info}"
  intake_rate_limit="${AGENT_CONTROL_PLANE_INTAKE_RATE_LIMIT:-30}"
  events_transport="${AGENT_CONTROL_PLANE_EVENTS_TRANSPORT:-http}"
  mcp_transport="${AGENT_CONTROL_PLANE_MCP_TRANSPORT:-https}"
  certificate_source="${AGENT_CONTROL_PLANE_CERTIFICATE_SOURCE:-self_generated}"
  certfile="${AGENT_CONTROL_PLANE_CERTFILE:-}"
  keyfile="${AGENT_CONTROL_PLANE_KEYFILE:-}"
fi

external_tls_error=""
if { [ "${events_transport}" = "https" ] || [ "${mcp_transport}" = "https" ]; } && [ "${certificate_source}" = "external" ]; then
  if stage_output="$(PYTHONPATH=/app/src python3 -c 'from pathlib import Path; from agent_control_plane.tls import stage_external_certificate; import sys; stage_external_certificate(sys.argv[1],sys.argv[2],Path("/run/agent-control-plane-external-tls"),1000,1000)' "${certfile}" "${keyfile}" 2>&1)"; then
    certfile="server-cert.pem";keyfile="server-key.pem"
  else
    external_tls_error="$(printf '%s\n' "${stage_output}" | tail -n 1)";certfile="server-cert.pem";keyfile="server-key.pem"
    export AGENT_CONTROL_PLANE_EXTERNAL_TLS_STAGE_ERROR="${external_tls_error}"
  fi
  export AGENT_CONTROL_PLANE_EXTERNAL_TLS_DIR=/run/agent-control-plane-external-tls
fi

export AGENT_CONTROL_PLANE_DATA_DIR="${AGENT_CONTROL_PLANE_DATA_DIR:-/data}"
export AGENT_CONTROL_PLANE_LOG_LEVEL="${log_level}"
export AGENT_CONTROL_PLANE_INTAKE_RATE_LIMIT="${intake_rate_limit}"
export AGENT_CONTROL_PLANE_CREDENTIAL_PEPPER_HEX="${pepper_hex}"
export AGENT_CONTROL_PLANE_EVENTS_TRANSPORT="${events_transport}"
export AGENT_CONTROL_PLANE_MCP_TRANSPORT="${mcp_transport}"
export AGENT_CONTROL_PLANE_CERTIFICATE_SOURCE="${certificate_source}"
export AGENT_CONTROL_PLANE_CERTFILE="${certfile}"
export AGENT_CONTROL_PLANE_KEYFILE="${keyfile}"
export PYTHONPATH=/app/src

log_info() {
  timestamp="$(python3 -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec="seconds"))')"
  printf '%s [Agent Control Plane] INFO: %s\n' "${timestamp}" "$*"
}

log_error() {
  timestamp="$(python3 -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec="seconds"))')"
  printf '%s [Agent Control Plane] ERROR: %s\n' "${timestamp}" "$*" >&2
}

log_warning() {
  timestamp="$(python3 -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec="seconds"))')"
  printf '%s [Agent Control Plane] WARNING: %s\n' "${timestamp}" "$*" >&2
}

log_info "Initializing Agent Control Plane database schema"
su-exec agent-control-plane:agent-control-plane python3 -m agent_control_plane.database initialize

admin_pid=""
events_pid=""
mcp_pid=""

stop_servers() {
  for pid in "${admin_pid}" "${events_pid}" "${mcp_pid}"; do
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

tls_ready=false
tls_values=""
if [ "${events_transport}" = "https" ] || [ "${mcp_transport}" = "https" ]; then
  if [ -n "${external_tls_error}" ]; then
    log_error "Public TLS certificate is invalid; HTTPS listeners were not started and Ingress administration remains available error=${external_tls_error}"
  elif tls_values="$(su-exec agent-control-plane:agent-control-plane python3 -c 'from agent_control_plane.settings import load_settings; from agent_control_plane.tls import prepare_certificate; s=load_settings(); i=prepare_certificate(s.data_dir,s.certificate_source,s.certfile,s.keyfile); print(i.certfile); print(i.keyfile); print(i.fingerprint_sha256); print(i.not_after)' 2>&1)"; then
    tls_ready=true
    tls_cert_path="$(printf '%s\n' "${tls_values}" | sed -n '1p')"
    tls_key_path="$(printf '%s\n' "${tls_values}" | sed -n '2p')"
    tls_fingerprint="$(printf '%s\n' "${tls_values}" | sed -n '3p')"
    tls_expiry="$(printf '%s\n' "${tls_values}" | sed -n '4p')"
    log_info "Public TLS certificate source: ${certificate_source}"
    log_info "Public TLS certificate SHA-256: ${tls_fingerprint}"
    log_info "Public TLS certificate expires at: ${tls_expiry}"
  else
    tls_error="$(printf '%s\n' "${tls_values}" | tail -n 1)"
    log_error "Public TLS certificate is invalid; HTTPS listeners were not started and Ingress administration remains available error=${tls_error}"
  fi
fi

if [ "${events_transport}" = "http" ]; then
  log_info "Event Intake API listening on HTTP port 8100, path /api/v1/events"
  log_warning "Event Intake API uses unencrypted HTTP; credentials and event payloads are not encrypted by this application"
  su-exec agent-control-plane:agent-control-plane env AGENT_CONTROL_PLANE_SURFACE=events \
    python3 -m uvicorn agent_control_plane.main:app --host 0.0.0.0 --port 8100 \
    --no-access-log --log-level "${log_level}" --log-config /app/src/agent_control_plane/uvicorn_logging.json &
  events_pid=$!
elif [ "${tls_ready}" = true ]; then
  log_info "Event Intake API listening on HTTPS port 8100, path /api/v1/events"
  su-exec agent-control-plane:agent-control-plane env AGENT_CONTROL_PLANE_SURFACE=events \
    python3 -m uvicorn agent_control_plane.main:app --host 0.0.0.0 --port 8100 \
    --ssl-certfile "${tls_cert_path}" --ssl-keyfile "${tls_key_path}" \
    --no-access-log --log-level "${log_level}" --log-config /app/src/agent_control_plane/uvicorn_logging.json &
  events_pid=$!
fi

if [ "${mcp_transport}" = "http" ]; then
  log_info "MCP Worker Endpoint listening on HTTP port 8098, path /mcp"
  log_warning "MCP Worker Endpoint uses unencrypted HTTP; worker credentials, jobs, leases, and reports are not encrypted by this application"
  su-exec agent-control-plane:agent-control-plane env AGENT_CONTROL_PLANE_SURFACE=mcp \
    python3 -m uvicorn agent_control_plane.main:app --host 0.0.0.0 --port 8098 \
    --no-access-log --log-level "${log_level}" --log-config /app/src/agent_control_plane/uvicorn_logging.json &
  mcp_pid=$!
elif [ "${tls_ready}" = true ]; then
  log_info "MCP Worker Endpoint listening on HTTPS port 8098, path /mcp"
  su-exec agent-control-plane:agent-control-plane env AGENT_CONTROL_PLANE_SURFACE=mcp \
    python3 -m uvicorn agent_control_plane.main:app --host 0.0.0.0 --port 8098 \
    --ssl-certfile "${tls_cert_path}" --ssl-keyfile "${tls_key_path}" \
    --no-access-log --log-level "${log_level}" --log-config /app/src/agent_control_plane/uvicorn_logging.json &
  mcp_pid=$!
fi

while true; do
  for pid in "${admin_pid}" "${events_pid}" "${mcp_pid}"; do
    [ -z "${pid}" ] && continue
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
