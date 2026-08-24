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
su-exec agent-execution-plane:agent-execution-plane env PYTHONPATH=/app/src \
  python3 -c 'from pathlib import Path; from agent_execution_plane.codex_runtime import ensure_codex_home; ensure_codex_home(Path("/data/private/codex-home"))'

if [ -f /data/options.json ]; then
  log_level="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("log_level", "info"))')"
  public_transport="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("public_transport", "https"))')"
  certificate_source="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("certificate_source", "self_generated"))')"
  certfile="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("certfile", ""))')"
  keyfile="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("keyfile", ""))')"
else
  log_level="${AGENT_EXECUTION_PLANE_LOG_LEVEL:-info}"
  public_transport="${AGENT_EXECUTION_PLANE_PUBLIC_TRANSPORT:-https}"
  certificate_source="${AGENT_EXECUTION_PLANE_CERTIFICATE_SOURCE:-self_generated}"
  certfile="${AGENT_EXECUTION_PLANE_CERTFILE:-}"
  keyfile="${AGENT_EXECUTION_PLANE_KEYFILE:-}"
fi
external_tls_error=""
export AGENT_EXECUTION_PLANE_DATA_DIR="${AGENT_EXECUTION_PLANE_DATA_DIR:-/data}"
export AGENT_EXECUTION_PLANE_LOG_LEVEL="${log_level}"
export AGENT_EXECUTION_PLANE_PUBLIC_TRANSPORT="${public_transport}"
export AGENT_EXECUTION_PLANE_CERTIFICATE_SOURCE="${certificate_source}"
export AGENT_EXECUTION_PLANE_CERTFILE="${certfile}"
export AGENT_EXECUTION_PLANE_KEYFILE="${keyfile}"

log() {
  timestamp="$(python3 -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec="seconds"))')"
  printf '%s [Agent Execution Plane] %s: %s\n' "${timestamp}" "$1" "$2"
}

log INFO "Initializing generation-1 database schema"
su-exec agent-execution-plane:agent-execution-plane python3 -m agent_execution_plane.database initialize

tls_ready=false
tls_values=""
if [ "${public_transport}" = "https" ]; then
  tls_probe="su-exec agent-execution-plane:agent-execution-plane"
  [ "${certificate_source}" != "external" ] || tls_probe=""
  if tls_values="$(${tls_probe} python3 -c 'from agent_execution_plane.settings import load_settings; from agent_execution_plane.tls import prepare_certificate; s=load_settings();i=prepare_certificate(s.data_dir,s.certificate_source,s.certfile,s.keyfile);print(i.certfile);print(i.keyfile);print(i.fingerprint_sha256);print(i.not_after);print(i.subject);print(i.issuer);print(i.not_before)' 2>&1)"; then
    tls_ready=true
    tls_cert_path="$(printf '%s\n' "${tls_values}"|sed -n '1p')";tls_key_path="$(printf '%s\n' "${tls_values}"|sed -n '2p')";tls_fingerprint="$(printf '%s\n' "${tls_values}"|sed -n '3p')";tls_expiry="$(printf '%s\n' "${tls_values}"|sed -n '4p')"
    export AGENT_EXECUTION_PLANE_TLS_FINGERPRINT="${tls_fingerprint}" AGENT_EXECUTION_PLANE_TLS_NOT_AFTER="${tls_expiry}" AGENT_EXECUTION_PLANE_TLS_SUBJECT="$(printf '%s\n' "${tls_values}"|sed -n '5p')" AGENT_EXECUTION_PLANE_TLS_ISSUER="$(printf '%s\n' "${tls_values}"|sed -n '6p')" AGENT_EXECUTION_PLANE_TLS_NOT_BEFORE="$(printf '%s\n' "${tls_values}"|sed -n '7p')"
  else
    external_tls_error="$(printf '%s\n' "${tls_values}"|tail -n 1)"
    export AGENT_EXECUTION_PLANE_EXTERNAL_TLS_ERROR="${external_tls_error}"
  fi
fi

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

if [ "${public_transport}" = "http" ]; then
  log WARNING "Standalone Execution API uses unencrypted HTTP; credentials, job inputs, and reports are not encrypted by this application"
  su-exec agent-execution-plane:agent-execution-plane env AGENT_EXECUTION_PLANE_SURFACE=api \
    python3 -m uvicorn agent_execution_plane.main:app --host 0.0.0.0 --port 8098 \
    --no-access-log --log-level "${log_level}" --log-config /app/src/agent_execution_plane/uvicorn_logging.json &
  api_pid=$!
else
  if [ "${tls_ready}" != true ]; then
    log ERROR "Public TLS certificate is invalid; Standalone Execution API was not started and Ingress administration remains available error=${external_tls_error}"
  else
    log INFO "Standalone Execution API listening on HTTPS port 8098"
    log INFO "Public TLS certificate source: ${certificate_source}"
    log INFO "Public TLS certificate SHA-256: ${tls_fingerprint}"
    log INFO "Public TLS certificate expires at: ${tls_expiry}"
    if [ "${certificate_source}" = "external" ]; then
      AGENT_EXECUTION_PLANE_SURFACE=api python3 -m agent_execution_plane.tls_server &
    else
      su-exec agent-execution-plane:agent-execution-plane env AGENT_EXECUTION_PLANE_SURFACE=api \
        python3 -m uvicorn agent_execution_plane.main:app --host 0.0.0.0 --port 8098 --ssl-certfile "${tls_cert_path}" --ssl-keyfile "${tls_key_path}" \
        --no-access-log --log-level "${log_level}" --log-config /app/src/agent_execution_plane/uvicorn_logging.json &
    fi
    api_pid=$!
  fi
fi

while true; do
  for pid in "${admin_pid}" "${api_pid}"; do
    [ -z "${pid}" ] && continue
    if ! kill -0 "${pid}" 2>/dev/null; then
      wait "${pid}" || status=$?
      log ERROR "An application listener stopped unexpectedly"
      exit "${status:-1}"
    fi
  done
  sleep 1
done
