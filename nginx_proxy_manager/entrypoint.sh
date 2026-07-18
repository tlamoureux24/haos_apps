#!/usr/bin/env bash
set -euo pipefail

# Home Assistant persists /data. NPM normally expects a second Docker volume at
# /etc/letsencrypt, so keep that directory inside the persistent app data too.
mkdir -p /data/letsencrypt

if [[ ! -L /etc/letsencrypt ]] || [[ "$(readlink /etc/letsencrypt)" != "/data/letsencrypt" ]]; then
  echo "FATAL: /etc/letsencrypt is not linked to /data/letsencrypt" >&2
  exit 1
fi

exec /init "$@"
