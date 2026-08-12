#!/usr/bin/with-contenv bashio
set -euo pipefail

readonly DATA_HOME="/data/home"
readonly USER_DATA="/data/vscode"

log_level="$(bashio::config 'log_level')"
bashio::log.level "${log_level}"

workspace_path="$(bashio::config 'workspace_path')"
case "${workspace_path}" in
  /data|/data/*|/config|/config/*|/addon_configs|/addon_configs/*|/addons|/addons/*|/share|/share/*)
    ;;
  *)
    bashio::exit.nok "workspace_path must be inside /data, /config, /addon_configs, /addons, or /share"
    ;;
esac

if [[ "${workspace_path}" == "/" ]]; then
  bashio::exit.nok "The root filesystem cannot be used as a workspace"
fi

mkdir -p \
  "${DATA_HOME}/.codex" \
  "${DATA_HOME}/.config" \
  "${DATA_HOME}/.ssh" \
  "${USER_DATA}/User" \
  "${USER_DATA}/extensions" \
  "${workspace_path}"
chmod 0700 "${DATA_HOME}/.codex" "${DATA_HOME}/.ssh"

# OAuth state and the normal workspace belong to the unprivileged Codex
# runtime. Existing files from 0.1.0/0.1.1 are migrated on first start.
chown codex:codex "${DATA_HOME}"
chown -R codex:codex \
  "${DATA_HOME}" \
  "${USER_DATA}" \
  "${workspace_path}"

if [[ ! -e "${USER_DATA}/User/settings.json" ]]; then
  cp /usr/local/share/studio-code-server/settings.json "${USER_DATA}/User/settings.json"
fi

# Add the safer development shell to existing installations without removing
# unrelated user settings or installed language-pack preferences.
settings_tmp="$(mktemp)"
jq \
  '.["terminal.integrated.defaultProfile.linux"] = "Codex workspace"
   | .["git.autofetch"] = true
   | .["terminal.integrated.profiles.linux"] = {
       "Codex workspace": {"path": "/bin/zsh"}
     }' \
  "${USER_DATA}/User/settings.json" > "${settings_tmp}"
mv "${settings_tmp}" "${USER_DATA}/User/settings.json"
chown codex:codex "${USER_DATA}/User/settings.json"

touch "${DATA_HOME}/.gitconfig" "${DATA_HOME}/.zsh_history" "${DATA_HOME}/.zshrc"
chmod 0600 "${DATA_HOME}/.zsh_history"
chown codex:codex "${DATA_HOME}/.gitconfig" "${DATA_HOME}/.zsh_history" "${DATA_HOME}/.zshrc"

ha_mcp_url="$(bashio::config 'ha_mcp_url')"
if [[ -n "${ha_mcp_url}" ]]; then
  if [[ ! "${ha_mcp_url}" =~ ^https?://[^[:space:]]+/private_[^/[:space:]]+$ ]]; then
    bashio::exit.nok "ha_mcp_url must be an HTTP(S) private HA-MCP URL ending in /private_<secret>"
  fi

  codex_mcp=(
    s6-setuidgid codex
    env
    -u HASS_TOKEN
    -u SUPERVISOR_TOKEN
    HOME="${DATA_HOME}"
    /usr/local/bin/codex-real
    mcp
  )
  "${codex_mcp[@]}" remove home-assistant >/dev/null 2>&1 || true
  "${codex_mcp[@]}" add home-assistant --url "${ha_mcp_url}" >/dev/null
  bashio::log.info "Configured the private Home Assistant MCP server for Codex"
fi

if bashio::config.has_value 'packages'; then
  mapfile -t packages < <(bashio::config 'packages')
  if (( ${#packages[@]} > 0 )); then
    bashio::log.info "Installing configured Debian packages..."
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"
    rm -rf /var/lib/apt/lists/*
  fi
fi

if bashio::config.has_value 'init_commands'; then
  while IFS= read -r command; do
    [[ -z "${command}" ]] && continue
    bashio::log.info "Running a configured initialization command"
    HOME="${DATA_HOME}" bash -o pipefail -c "${command}"
  done < <(bashio::config 'init_commands')
fi

export HOME="${DATA_HOME}"
export SHELL="/bin/zsh"
export HISTFILE="${DATA_HOME}/.zsh_history"
export HASS_SERVER="http://supervisor/core"

bashio::log.info "Starting Studio Code Server on the Home Assistant Ingress as unprivileged user codex"
bashio::log.info "Workspace: ${workspace_path}"
bashio::log.info "Codex CLI: $(codex --version)"
bashio::log.info "Codex runtime: unprivileged user codex (uid 1000), Supervisor token removed"
bashio::log.info "Editor, extensions, terminals, and Codex run as uid 1000 without Supervisor credentials"
bashio::log.info "Run 'codex login --device-auth' once from the integrated terminal"

cd "${workspace_path}"
exec s6-setuidgid codex \
  env \
  -u HASS_TOKEN \
  -u SUPERVISOR_TOKEN \
  HOME="${DATA_HOME}" \
  SHELL=/bin/zsh \
  HISTFILE="${DATA_HOME}/.zsh_history" \
  code-server \
  --host 0.0.0.0 \
  --port 1337 \
  --auth none \
  --disable-telemetry \
  --disable-update-check \
  --user-data-dir "${USER_DATA}" \
  --extensions-dir "${USER_DATA}/extensions" \
  "${workspace_path}"
