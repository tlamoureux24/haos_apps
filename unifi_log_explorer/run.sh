#!/usr/bin/with-contenv bashio
set -euo pipefail

python3 /app/unifi_log_explorer.py --prepare-secrets

export UNIFI_LOG_EXPLORER_SECRETS_PREPARED="1"
exec python3 /app/unifi_log_explorer.py
