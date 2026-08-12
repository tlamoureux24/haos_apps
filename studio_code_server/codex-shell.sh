#!/bin/bash
set -euo pipefail

# Default development shell: persistent home, unprivileged identity, and no
# inherited Home Assistant Supervisor credentials.
exec s6-setuidgid codex \
  env \
    -u HASS_TOKEN \
    -u SUPERVISOR_TOKEN \
    HOME=/data/home \
    SHELL=/bin/zsh \
    HISTFILE=/data/home/.zsh_history \
    /bin/zsh -l "$@"
