#!/usr/bin/with-contenv bashio
set -euo pipefail

export WEBHOOK_DISPLAY_PORT="37989"
if bashio::addon.port "37989/tcp" >/tmp/unifi_autoblock_port 2>/dev/null; then
  WEBHOOK_DISPLAY_PORT="$(cat /tmp/unifi_autoblock_port)"
  export WEBHOOK_DISPLAY_PORT
fi

rm -f /tmp/unifi_autoblock_clear_api_key_option
python3 /app/unifi_autoblock.py --prepare-secrets

if [[ -f /tmp/unifi_autoblock_clear_api_key_option ]]; then
  bashio::log.info "Clearing UniFi API key value from app configuration after local encryption"
  bashio::addon.option "unifi_api_key" ""
fi

export UNIFI_AUTOBLOCK_SECRETS_PREPARED="1"
python3 /app/unifi_autoblock.py
