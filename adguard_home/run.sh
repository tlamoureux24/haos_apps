#!/bin/sh
set -eu

readonly CONFIG_ROOT="/config"
readonly CONF_DIR="${CONFIG_ROOT}/conf"
readonly WORK_DIR="${CONFIG_ROOT}/work"
readonly CONFIG_FILE="${CONF_DIR}/AdGuardHome.yaml"

mkdir -p "${CONF_DIR}" "${WORK_DIR}"
chown -R nobody:nogroup "${CONF_DIR}" "${WORK_DIR}"

if [ ! -s "${CONFIG_FILE}" ]; then
  echo "[NOTICE] First-run setup requires temporary administrator privileges"
  echo "[NOTICE] AdGuard Home will restart automatically as nobody after setup"

  /opt/adguardhome/AdGuardHome \
    --no-check-update \
    --config "${CONFIG_FILE}" \
    --work-dir "${WORK_DIR}" &
  child_pid=$!

  trap 'kill -TERM "${child_pid}" 2>/dev/null || true' TERM INT

  while kill -0 "${child_pid}" 2>/dev/null; do
    if [ -s "${CONFIG_FILE}" ]; then
      echo "[INFO] Initial configuration created; dropping privileges"
      sleep 2
      kill -TERM "${child_pid}" 2>/dev/null || true
      wait "${child_pid}" || true
      trap - TERM INT
      chown -R nobody:nogroup "${CONF_DIR}" "${WORK_DIR}"
      break
    fi
    sleep 1
  done

  if kill -0 "${child_pid}" 2>/dev/null; then
    kill -TERM "${child_pid}" 2>/dev/null || true
    wait "${child_pid}" || true
  elif [ ! -s "${CONFIG_FILE}" ]; then
    if wait "${child_pid}"; then
      exit 0
    else
      status=$?
      exit "${status}"
    fi
  fi
fi

echo "[INFO] Starting AdGuard Home as an unprivileged user"
exec su-exec nobody:nogroup /opt/adguardhome/AdGuardHome \
  --no-check-update \
  --config "${CONFIG_FILE}" \
  --work-dir "${WORK_DIR}"
