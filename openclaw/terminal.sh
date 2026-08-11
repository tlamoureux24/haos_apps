#!/usr/bin/env bash
set -euo pipefail

cd "${OPENCLAW_WORKSPACE_DIR:-/config/workspace}"
export PS1='openclaw@haos:\w$ '

echo "OpenClaw administrative CLI"
echo "This shell runs as the unprivileged node user and is available only through Home Assistant Ingress."
echo "Example: openclaw devices list"
exec /bin/bash --noprofile --norc -i
