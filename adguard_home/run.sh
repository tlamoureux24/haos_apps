#!/bin/sh
set -eu

readonly CONFIG_ROOT="/config"
readonly CONF_DIR="${CONFIG_ROOT}/conf"
readonly WORK_DIR="${CONFIG_ROOT}/work"
readonly CONFIG_FILE="${CONF_DIR}/AdGuardHome.yaml"

mkdir -p "${CONF_DIR}" "${WORK_DIR}"
chown -R nobody:nogroup "${CONF_DIR}" "${WORK_DIR}"

echo "[INFO] Starting AdGuard Home as an unprivileged user"
exec su-exec nobody:nogroup /opt/adguardhome/AdGuardHome \
  --no-check-update \
  --config "${CONFIG_FILE}" \
  --work-dir "${WORK_DIR}"
