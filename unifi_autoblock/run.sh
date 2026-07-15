#!/usr/bin/with-contenv bashio
set -euo pipefail

export WEBHOOK_DISPLAY_PORT="37989"
if bashio::addon.port "37989/tcp" >/tmp/unifi_autoblock_port 2>/dev/null; then
  WEBHOOK_DISPLAY_PORT="$(cat /tmp/unifi_autoblock_port)"
  export WEBHOOK_DISPLAY_PORT
fi

python3 /app/unifi_autoblock.py --prepare-secrets

export UNIFI_AUTOBLOCK_SECRETS_PREPARED="1"
python3 /app/unifi_autoblock.py
