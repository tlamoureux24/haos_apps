#!/bin/bash
set -euo pipefail

# Run the real Codex binary with the persistent user home and without inherited
# Home Assistant Supervisor credentials. Root callers are reduced to the same
# UID used by code-server; interactive callers are already that user.
codex_env=(
  env
  -u HASS_TOKEN
  -u SUPERVISOR_TOKEN
  HOME=/data/home
  SHELL=/bin/zsh
  HISTFILE=/data/home/.zsh_history
  /usr/local/bin/codex-real
)

case "$(id -u)" in
  0)
    exec s6-setuidgid codex "${codex_env[@]}" "$@"
    ;;
  1000)
    exec "${codex_env[@]}" "$@"
    ;;
  *)
    echo "codex: unsupported runtime uid $(id -u); expected root or codex (1000)" >&2
    exit 1
    ;;
esac
