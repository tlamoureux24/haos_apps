#!/bin/bash
set -euo pipefail

# Keep the administrative code-server terminal separate from the agent runtime.
# Codex and every command it launches run as the dedicated unprivileged user and
# do not inherit the Home Assistant Supervisor bearer token.
exec s6-setuidgid codex \
  env \
    -u HASS_TOKEN \
    -u SUPERVISOR_TOKEN \
    HOME=/data/home \
    SHELL=/bin/zsh \
    HISTFILE=/data/home/.zsh_history \
    /usr/local/bin/codex-real "$@"
