#!/bin/bash
set -euo pipefail

# Keep the administrative code-server terminal separate from the agent runtime.
# From a root terminal, drop privileges once. From the default Codex terminal,
# the process is already UID 1000 and must not attempt setgroups again.
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
