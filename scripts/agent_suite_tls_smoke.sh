#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
network="agent-suite-tls-$RANDOM"
containers=()
volumes=()

cleanup() {
  for container in "${containers[@]}"; do
    docker rm --force "${container}" >/dev/null 2>&1 || true
  done
  docker network rm "${network}" >/dev/null 2>&1 || true
  for volume in "${volumes[@]}"; do
    docker volume rm "${volume}" >/dev/null 2>&1 || true
  done
  rm -rf "${work}"
}
trap cleanup EXIT

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
pass() { printf 'PASS: %s\n' "$*"; }

version() { sed -n 's/^version: "\([^"]*\)"$/\1/p' "${root}/$1/config.yaml"; }

build_image() {
  local app=$1 image=$2 app_version
  app_version="$(version "${app}")"
  if [ "${GITHUB_ACTIONS:-}" = true ]; then
    docker buildx build --load \
      --cache-from "type=gha,scope=${image}-amd64" \
      --build-arg BUILD_ARCH=amd64 \
      --build-arg "BUILD_VERSION=${app_version}" \
      --tag "${image}:${app_version}" "${root}/${app}" >/dev/null
  else
    docker build --build-arg BUILD_ARCH=amd64 --build-arg "BUILD_VERSION=${app_version}" \
      --tag "${image}:${app_version}" "${root}/${app}" >/dev/null
  fi
}

wait_url() {
  local url=$1 header=${2:-}
  for _ in {1..90}; do
    if [ -n "${header}" ]; then
      curl --fail --silent --show-error --insecure -H "${header}" "${url}" >/dev/null 2>&1 && return 0
    else
      curl --fail --silent --show-error --insecure "${url}" >/dev/null 2>&1 && return 0
    fi
    sleep 1
  done
  return 1
}

fingerprint() {
  local port=$1
  openssl s_client -connect "127.0.0.1:${port}" -servername localhost </dev/null 2>/dev/null |
    openssl x509 -noout -fingerprint -sha256 | sed 's/^sha256 Fingerprint=//I'
}

assert_plaintext_rejected() {
  local port=$1 code
  code="$(curl --max-time 3 --silent --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:${port}/health/ready" || true)"
  [ "${code}" = 000 ] || fail "plaintext HTTP was accepted by TLS port ${port} (status ${code})"
}

docker network create "${network}" >/dev/null
gateway="$(docker network inspect "${network}" --format '{{(index .IPAM.Config 0).Gateway}}')"

build_image agent_control_plane agent-control-plane
build_image agent_execution_plane agent-execution-plane
build_image mcp_capability_bridge mcp-capability-bridge

# Generated certificates: real TLS sockets, log metadata, key permissions and persistence.
run_generated() {
  local label=$1 image=$2 prefix=$3 public_port=$4 admin_port=$5 ingress_env=$6
  local app_version name volume first second logs
  app_version="$(version "${label}")"
  name="tls-${prefix,,}-generated"
  volume="${name}-data"
  containers+=("${name}"); volumes+=("${volume}")
  docker volume create "${volume}" >/dev/null
  docker run --detach --name "${name}" --network "${network}" \
    --env "${ingress_env}=${gateway}" \
    --publish "127.0.0.1:${public_port}:8098" --publish "127.0.0.1:${admin_port}:8099" \
    --volume "${volume}:/data" "${image}:${app_version}" >/dev/null
  wait_url "https://127.0.0.1:${public_port}/health/ready" || fail "${prefix} generated HTTPS listener did not start"
  wait_url "http://127.0.0.1:${admin_port}/health/ready" "X-Ingress-Path: /api/hassio_ingress/tls" || fail "${prefix} admin listener did not start"
  first="$(fingerprint "${public_port}")"; [ -n "${first}" ] || fail "${prefix} has no live certificate fingerprint"
  assert_plaintext_rejected "${public_port}"
  logs="$(docker logs "${name}" 2>&1)"
  grep -F 'Public TLS certificate source: self_generated' <<<"${logs}" >/dev/null || fail "${prefix} omitted TLS source log"
  grep -F "Public TLS certificate SHA-256: ${first}" <<<"${logs}" >/dev/null || fail "${prefix} logged fingerprint differs from live certificate"
  docker exec "${name}" /bin/sh -c "test \"\$(stat -c '%a' /data/private/tls/server-key.pem)\" = 600" || fail "${prefix} private key mode is not 0600"
  docker rm --force "${name}" >/dev/null
  docker run --detach --name "${name}" --network "${network}" \
    --env "${ingress_env}=${gateway}" \
    --publish "127.0.0.1:${public_port}:8098" --publish "127.0.0.1:${admin_port}:8099" \
    --volume "${volume}:/data" "${image}:${app_version}" >/dev/null
  wait_url "https://127.0.0.1:${public_port}/health/ready" || fail "${prefix} did not restart with persistent certificate"
  second="$(fingerprint "${public_port}")"
  [ "${first}" = "${second}" ] || fail "${prefix} generated certificate changed across restart"
  pass "${prefix}: generated HTTPS, live fingerprint, permissions, plaintext rejection, persistence"
}

run_generated agent_execution_plane agent-execution-plane AEP 19098 19099 AGENT_EXECUTION_PLANE_INGRESS_PROXY_IP
run_generated mcp_capability_bridge mcp-capability-bridge MCB 19198 19199 MCP_CAPABILITY_BRIDGE_INGRESS_PROXY_IP

# ACP default topology: events over HTTP on 8100, MCP over HTTPS on 8098, admin on 8099.
acp_version="$(version agent_control_plane)"
acp_name=tls-acp-default; acp_volume=tls-acp-default-data
containers+=("${acp_name}"); volumes+=("${acp_volume}"); docker volume create "${acp_volume}" >/dev/null
docker run --detach --name "${acp_name}" --network "${network}" \
  --env "AGENT_CONTROL_PLANE_INGRESS_PROXY_IP=${gateway}" \
  -p 127.0.0.1:19298:8098 -p 127.0.0.1:19299:8099 -p 127.0.0.1:19300:8100 \
  -v "${acp_volume}:/data" "agent-control-plane:${acp_version}" >/dev/null
wait_url https://127.0.0.1:19298/health/ready || fail 'ACP MCP HTTPS listener did not start'
wait_url http://127.0.0.1:19300/health/ready || fail 'ACP Event HTTP listener did not start'
wait_url http://127.0.0.1:19299/health/ready 'X-Ingress-Path: /api/hassio_ingress/tls' || fail 'ACP admin listener did not start'
[ "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:19300/mcp)" = 404 ] || fail 'ACP MCP route leaked onto Event port'
[ "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:19300/api/v1/jobs)" = 404 ] || fail 'ACP worker API leaked onto Event port'
[ "$(curl -ksS -o /dev/null -w '%{http_code}' https://127.0.0.1:19298/admin/api/v1/status)" = 404 ] || fail 'ACP administration route leaked onto MCP port'
grep -F 'Event Intake API uses unencrypted HTTP' < <(docker logs "${acp_name}" 2>&1) >/dev/null || fail 'ACP omitted Event HTTP warning'
assert_plaintext_rejected 19298
pass 'ACP: default split transports and route isolation'

# ACP both-HTTPS surfaces must present the same shared certificate.
docker rm --force "${acp_name}" >/dev/null
docker run --detach --name "${acp_name}" --network "${network}" \
  --env "AGENT_CONTROL_PLANE_INGRESS_PROXY_IP=${gateway}" \
  --env AGENT_CONTROL_PLANE_EVENTS_TRANSPORT=https --env AGENT_CONTROL_PLANE_MCP_TRANSPORT=https \
  -p 127.0.0.1:19298:8098 -p 127.0.0.1:19299:8099 -p 127.0.0.1:19300:8100 \
  -v "${acp_volume}:/data" "agent-control-plane:${acp_version}" >/dev/null
wait_url https://127.0.0.1:19298/health/ready || fail 'ACP MCP all-HTTPS listener did not start'
wait_url https://127.0.0.1:19300/health/ready || fail 'ACP Event all-HTTPS listener did not start'
[ "$(fingerprint 19298)" = "$(fingerprint 19300)" ] || fail 'ACP HTTPS surfaces do not share one certificate'
ingress_path=/api/hassio_ingress/tls
admin_page="$(curl -fsS -H "X-Ingress-Path: ${ingress_path}" http://127.0.0.1:19299/)"
csrf_token="$(sed -n 's/.*data-csrf="\([^"]*\)".*/\1/p' <<<"${admin_page}")"
[ -n "${csrf_token}" ] || fail 'ACP admin CSRF token was not issued'
identity="$(curl -fsS -X POST -H "X-Ingress-Path: ${ingress_path}" -H "X-CSRF-Token: ${csrf_token}" \
  -H "Cookie: acp_csrf=${csrf_token}" -H 'Content-Type: application/json' \
  --data '{"display_name":"TLS event producer","identity_type":"event_source","actions":["events.create"]}' \
  http://127.0.0.1:19299/admin/api/v1/identities)"
event_credential="$(jq -er '.credential' <<<"${identity}")"
source_identity_id="$(jq -er '.identity_id' <<<"${identity}")"
docker cp "${root}/scripts/seed_acp_tls_event.py" "${acp_name}:/tmp/seed_acp_tls_event.py"
docker exec --env PYTHONPATH=/app/src "${acp_name}" su-exec agent-control-plane:agent-control-plane \
  python3 /tmp/seed_acp_tls_event.py "${source_identity_id}"
occurred_at="$(date --utc +'%Y-%m-%dT%H:%M:%SZ')"
event_payload="$(jq -nc --arg occurred_at "${occurred_at}" '{schema_version:1,event_type:"service.alert",occurred_at:$occurred_at,subject:{service_id:"tls-docker-service"},attributes:{status:"unavailable"}}')"
event_status="$(curl -ksS -o "${work}/event-response.json" -w '%{http_code}' -X POST \
  -H "Authorization: Bearer ${event_credential}" -H 'Idempotency-Key: tls-integration-event' \
  -H 'Content-Type: application/json' --data "${event_payload}" https://127.0.0.1:19300/api/v1/events)"
[ "${event_status}" = 202 ] || fail "ACP authenticated HTTPS event intake returned ${event_status}: $(tr -d '\n' < "${work}/event-response.json")"
jq -e '.event_id and .job_id and (.status | type == "string")' "${work}/event-response.json" >/dev/null || fail "ACP HTTPS event was not queued: $(tr -d '\n' < "${work}/event-response.json")"
pass 'ACP: shared certificate and authenticated HTTPS Event Intake flow'

# HTTP compatibility and mandatory English warning for AEP and Bridge.
run_http() {
  local label=$1 image=$2 prefix=$3 port=$4 ingress_env=$5 transport_env=$6 warning=$7 app_version name volume
  app_version="$(version "${label}")"; name="tls-${prefix,,}-http"; volume="${name}-data"
  containers+=("${name}"); volumes+=("${volume}"); docker volume create "${volume}" >/dev/null
  docker run -d --name "${name}" --network "${network}" --env "${ingress_env}=${gateway}" --env "${transport_env}=http" \
    -p "127.0.0.1:${port}:8098" -v "${volume}:/data" "${image}:${app_version}" >/dev/null
  wait_url "http://127.0.0.1:${port}/health/ready" || fail "${prefix} HTTP compatibility listener did not start"
  grep -F "${warning}" < <(docker logs "${name}" 2>&1) >/dev/null || fail "${prefix} omitted unencrypted warning"
  pass "${prefix}: explicit HTTP compatibility and warning"
}
run_http agent_execution_plane agent-execution-plane AEP 19498 AGENT_EXECUTION_PLANE_INGRESS_PROXY_IP AGENT_EXECUTION_PLANE_PUBLIC_TRANSPORT 'Standalone Execution API uses unencrypted HTTP'
run_http mcp_capability_bridge mcp-capability-bridge MCB 19598 MCP_CAPABILITY_BRIDGE_INGRESS_PROXY_IP MCP_CAPABILITY_BRIDGE_PUBLIC_TRANSPORT 'MCP endpoint uses unencrypted HTTP'

# A mismatched external key must suppress only the HTTPS listener; Ingress remains reachable.
mkdir -p "${work}/ssl"
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj /CN=localhost -keyout "${work}/ssl/key-a.pem" -out "${work}/ssl/cert.pem" >/dev/null 2>&1
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj /CN=localhost -keyout "${work}/ssl/key-b.pem" -out "${work}/ssl/unused.pem" >/dev/null 2>&1
chmod 644 "${work}/ssl"/*.pem

run_invalid_external() {
  local label=$1 image=$2 prefix=$3 public_port=$4 admin_port=$5 ingress_env=$6 source_env=$7 cert_env=$8 key_env=$9 app_version name volume
  app_version="$(version "${label}")"; name="tls-${prefix,,}-invalid"; volume="${name}-data"
  containers+=("${name}"); volumes+=("${volume}"); docker volume create "${volume}" >/dev/null
  docker run -d --name "${name}" --network "${network}" --env "${ingress_env}=${gateway}" \
    --env "${source_env}=external" --env "${cert_env}=cert.pem" --env "${key_env}=key-b.pem" \
    -p "127.0.0.1:${public_port}:8098" -p "127.0.0.1:${admin_port}:8099" \
    -v "${volume}:/data" -v "${work}/ssl:/ssl:ro" "${image}:${app_version}" >/dev/null
  wait_url "http://127.0.0.1:${admin_port}/health/ready" 'X-Ingress-Path: /api/hassio_ingress/tls' || fail "${prefix} Ingress unavailable after TLS failure"
  ! curl --max-time 2 -ksSf "https://127.0.0.1:${public_port}/health/ready" >/dev/null 2>&1 || fail "${prefix} invalid HTTPS listener started"
  grep -F 'Ingress administration remains available' < <(docker logs "${name}" 2>&1) >/dev/null || fail "${prefix} TLS failure log is not actionable"
  pass "${prefix}: invalid external certificate is contained to public listener"
}
run_invalid_external agent_execution_plane agent-execution-plane AEP 19698 19699 AGENT_EXECUTION_PLANE_INGRESS_PROXY_IP AGENT_EXECUTION_PLANE_CERTIFICATE_SOURCE AGENT_EXECUTION_PLANE_CERTFILE AGENT_EXECUTION_PLANE_KEYFILE
run_invalid_external mcp_capability_bridge mcp-capability-bridge MCB 19798 19799 MCP_CAPABILITY_BRIDGE_INGRESS_PROXY_IP MCP_CAPABILITY_BRIDGE_CERTIFICATE_SOURCE MCP_CAPABILITY_BRIDGE_CERTFILE MCP_CAPABILITY_BRIDGE_KEYFILE
run_invalid_external agent_control_plane agent-control-plane ACP 19898 19899 AGENT_CONTROL_PLANE_INGRESS_PROXY_IP AGENT_CONTROL_PLANE_CERTIFICATE_SOURCE AGENT_CONTROL_PLANE_CERTFILE AGENT_CONTROL_PLANE_KEYFILE

printf '\nAll Agent Suite TLS Docker smoke tests passed.\n'
