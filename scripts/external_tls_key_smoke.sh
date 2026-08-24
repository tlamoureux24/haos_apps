#!/usr/bin/env bash
set -euo pipefail

kind="${1:?usage: external_tls_key_smoke.sh KIND IMAGE}"
image="${2:?usage: external_tls_key_smoke.sh KIND IMAGE}"
root="$(mktemp -d)"
name="external-tls-${kind}-smoke"

cleanup() {
  docker logs "${name}" 2>&1 || true
  docker rm -f "${name}" >/dev/null 2>&1 || true
  docker run --rm --entrypoint /bin/rm --volume "${root}:/cleanup" "${image}" \
    -f /cleanup/cert.pem /cleanup/key.pem >/dev/null 2>&1 || true
  rmdir "${root}" 2>/dev/null || true
}
trap cleanup EXIT

openssl req -x509 -newkey rsa:2048 -sha256 -days 2 -nodes \
  -keyout "${root}/key.pem" -out "${root}/cert.pem" -subj /CN=localhost \
  -addext basicConstraints=critical,CA:FALSE \
  -addext extendedKeyUsage=serverAuth \
  -addext subjectAltName=DNS:localhost >/dev/null 2>&1
chmod 0600 "${root}/key.pem"
chmod 0644 "${root}/cert.pem"
docker run --rm --entrypoint /bin/chown --volume "${root}:/tls" "${image}" \
  0:0 /tls/key.pem /tls/cert.pem

common=(--detach --name "${name}" --tmpfs /data:rw,mode=0755
  --volume "${root}/cert.pem:/ssl/cert.pem:ro"
  --volume "${root}/key.pem:/ssl/key.pem:ro")
case "${kind}" in
  acp)
    docker run "${common[@]}" -p 127.0.0.1:28098:8098 -p 127.0.0.1:28100:8100 \
      -e AGENT_CONTROL_PLANE_EVENTS_TRANSPORT=https -e AGENT_CONTROL_PLANE_MCP_TRANSPORT=https \
      -e AGENT_CONTROL_PLANE_CERTIFICATE_SOURCE=external -e AGENT_CONTROL_PLANE_CERTFILE=cert.pem \
      -e AGENT_CONTROL_PLANE_KEYFILE=key.pem "${image}" >/dev/null
    ports=(28098 28100); process_module=agent_control_plane.tls_server; runtime_user=agent-control-plane
    ;;
  aep)
    docker run "${common[@]}" -p 127.0.0.1:28098:8098 \
      -e AGENT_EXECUTION_PLANE_PUBLIC_TRANSPORT=https -e AGENT_EXECUTION_PLANE_CERTIFICATE_SOURCE=external \
      -e AGENT_EXECUTION_PLANE_CERTFILE=cert.pem -e AGENT_EXECUTION_PLANE_KEYFILE=key.pem "${image}" >/dev/null
    ports=(28098); process_module=agent_execution_plane.tls_server; runtime_user=agent-execution-plane
    ;;
  bridge)
    docker run "${common[@]}" -p 127.0.0.1:28098:8098 \
      -e MCP_CAPABILITY_BRIDGE_PUBLIC_TRANSPORT=https -e MCP_CAPABILITY_BRIDGE_CERTIFICATE_SOURCE=external \
      -e MCP_CAPABILITY_BRIDGE_CERTFILE=cert.pem -e MCP_CAPABILITY_BRIDGE_KEYFILE=key.pem "${image}" >/dev/null
    ports=(28098); process_module=mcp_capability_bridge.runtime; runtime_user=mcp-capability-bridge
    ;;
  *) echo "unknown kind: ${kind}" >&2; exit 2 ;;
esac

for port in "${ports[@]}"; do
  for attempt in {1..60}; do
    curl -kfsS "https://127.0.0.1:${port}/health/ready" >/dev/null 2>&1 && break
    [ "${attempt}" != 60 ] || exit 1
    sleep 1
  done
done

test "$(docker exec "${name}" /bin/sh -c 'stat -c %u /ssl/key.pem')" = 0
docker exec "${name}" su-exec "${runtime_user}:${runtime_user}" test ! -r /ssl/key.pem
uids="$(docker exec "${name}" /bin/sh -c "for process in /proc/[0-9]*; do command=\$(tr '\\0' ' ' < \"\${process}/cmdline\" 2>/dev/null || true); case \"\${command}\" in *python3\\ -m\\ ${process_module}*) stat -c %u \"\${process}\";; esac; done")"
test -n "${uids}"
test "$(printf '%s\n' "${uids}" | sort -u)" = 1000
docker exec "${name}" /bin/sh -c \
  '! find /run /data -path "*external-tls*" -print 2>/dev/null | grep -q .'
