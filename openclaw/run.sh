#!/usr/bin/env bash
set -euo pipefail

readonly OPTIONS_FILE="/data/options.json"
readonly APP_CONFIG_ROOT="/config"

if [[ ! -f "${OPTIONS_FILE}" ]]; then
  echo "FATAL: Home Assistant options are missing at ${OPTIONS_FILE}" >&2
  exit 1
fi

umask 077

export HOME="${APP_CONFIG_ROOT}"
export OPENCLAW_HOME="${APP_CONFIG_ROOT}"
export OPENCLAW_STATE_DIR="${APP_CONFIG_ROOT}/.openclaw"
export OPENCLAW_CONFIG_DIR="${OPENCLAW_STATE_DIR}"
export OPENCLAW_CONFIG_PATH="${OPENCLAW_STATE_DIR}/openclaw.json"
export OPENCLAW_WORKSPACE_DIR="${APP_CONFIG_ROOT}/workspace"
export XDG_CONFIG_HOME="${APP_CONFIG_ROOT}/.config"
export OPENCLAW_AUTH_PROFILE_SECRET_DIR="${XDG_CONFIG_HOME}/openclaw"

install -d -m 0700 -o node -g node \
  "${OPENCLAW_STATE_DIR}" \
  "${OPENCLAW_WORKSPACE_DIR}" \
  "${XDG_CONFIG_HOME}" \
  "${OPENCLAW_AUTH_PROFILE_SECRET_DIR}"

# Never allow an inherited API key to turn this subscription-only deployment
# into metered OpenAI Platform usage. OAuth credentials remain in OpenClaw's
# persistent auth profile store and are unaffected.
unset OPENAI_API_KEY CODEX_API_KEY OPENAI_ADMIN_KEY OPENAI_PROJECT_ID
for forbidden_key in OPENAI_API_KEY CODEX_API_KEY OPENAI_ADMIN_KEY OPENAI_PROJECT_ID; do
  if [[ -v "${forbidden_key}" ]]; then
    echo "FATAL: failed to remove forbidden OpenAI Platform variable ${forbidden_key}" >&2
    exit 1
  fi
done
echo "Verified subscription-only environment: OpenAI Platform API variables are absent."

eval "$(python3 /usr/local/lib/ha-openclaw-configure.py shell-env "${OPTIONS_FILE}" "${APP_CONFIG_ROOT}")"
export TZ OPENCLAW_GATEWAY_TOKEN

python3 /usr/local/lib/ha-openclaw-configure.py apply \
  "${OPTIONS_FILE}" "${OPENCLAW_CONFIG_PATH}" "${OPENCLAW_WORKSPACE_DIR}"

chown -R node:node \
  "${OPENCLAW_STATE_DIR}" \
  "${OPENCLAW_WORKSPACE_DIR}" \
  "${XDG_CONFIG_HOME}"

echo "Starting admin-only OpenClaw CLI on the Home Assistant Ingress."
gosu node ttyd -W -p 7681 -i 0.0.0.0 /usr/local/bin/ha-openclaw-shell &
terminal_pid=$!

echo "Starting OpenClaw ${OPENCLAW_UPSTREAM_VERSION} with HTTPS/WSS on port 18789."
echo "OpenAI Platform API keys are disabled; configure OpenAI with ChatGPT/Codex OAuth."

gosu node node /app/dist/index.js gateway --bind lan --port 18789 &
gateway_pid=$!

terminate() {
  kill -TERM "${gateway_pid}" "${terminal_pid}" 2>/dev/null || true
}
trap terminate INT TERM

set +e
wait -n "${gateway_pid}" "${terminal_pid}"
status=$?
set -e
terminate
wait "${gateway_pid}" "${terminal_pid}" 2>/dev/null || true
exit "${status}"
