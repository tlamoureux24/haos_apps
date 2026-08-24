#!/usr/bin/with-contenv /bin/sh
set -eu

runtime_uid=1000
runtime_gid=1000
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/app/src

chown "${runtime_uid}:${runtime_gid}" /data
su-exec mcp-capability-bridge:mcp-capability-bridge install -d -m 0700 /data/private
su-exec mcp-capability-bridge:mcp-capability-bridge env PYTHONPATH=/app/src \
  python3 -c 'from pathlib import Path; from mcp_capability_bridge.security import load_or_create_key; load_or_create_key(Path("/data/private/credential-pepper")); load_or_create_key(Path("/data/private/target-secret-key"))'

if [ -f /data/options.json ]; then
  log_level="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("log_level", "info"))')"
  public_transport="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("public_transport", "https"))')"
  certificate_source="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("certificate_source", "self_generated"))')"
  certfile="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("certfile", ""))')"
  keyfile="$(python3 -c 'import json; print(json.load(open("/data/options.json", encoding="utf-8")).get("keyfile", ""))')"
else
  log_level="${MCP_CAPABILITY_BRIDGE_LOG_LEVEL:-info}"
  public_transport="${MCP_CAPABILITY_BRIDGE_PUBLIC_TRANSPORT:-https}"
  certificate_source="${MCP_CAPABILITY_BRIDGE_CERTIFICATE_SOURCE:-self_generated}"
  certfile="${MCP_CAPABILITY_BRIDGE_CERTFILE:-}"
  keyfile="${MCP_CAPABILITY_BRIDGE_KEYFILE:-}"
fi

if [ "${public_transport}" = "https" ] && [ "${certificate_source}" = "external" ]; then
  stage_output=""
  if ! stage_output="$(python3 -c 'from pathlib import Path; from mcp_capability_bridge.tls import stage_external_certificate; import sys; stage_external_certificate(sys.argv[1],sys.argv[2],Path("/run/mcp-capability-bridge-external-tls"),1000,1000)' "${certfile}" "${keyfile}" 2>&1)"; then
    export MCP_CAPABILITY_BRIDGE_EXTERNAL_TLS_STAGE_ERROR="$(printf '%s\n' "${stage_output}" | tail -n 1)"
  fi
  certfile="server-cert.pem";keyfile="server-key.pem"
  export MCP_CAPABILITY_BRIDGE_EXTERNAL_TLS_DIR=/run/mcp-capability-bridge-external-tls
fi

export MCP_CAPABILITY_BRIDGE_DATA_DIR="${MCP_CAPABILITY_BRIDGE_DATA_DIR:-/data}"
export MCP_CAPABILITY_BRIDGE_LOG_LEVEL="${log_level}"
export MCP_CAPABILITY_BRIDGE_PUBLIC_TRANSPORT="${public_transport}"
export MCP_CAPABILITY_BRIDGE_CERTIFICATE_SOURCE="${certificate_source}"
export MCP_CAPABILITY_BRIDGE_CERTFILE="${certfile}"
export MCP_CAPABILITY_BRIDGE_KEYFILE="${keyfile}"

timestamp="$(python3 -c 'from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec="seconds"))')"
printf '%s [MCP Capability Bridge] INFO: Initializing generation-1 database schema\n' "${timestamp}"
su-exec mcp-capability-bridge:mcp-capability-bridge \
  python3 -m mcp_capability_bridge.database initialize

exec su-exec mcp-capability-bridge:mcp-capability-bridge \
  python3 -m mcp_capability_bridge.runtime
