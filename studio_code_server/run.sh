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

if [[ ! -e "${USER_DATA}/User/settings.json" ]]; then
  cp /usr/local/share/studio-code-server/settings.json "${USER_DATA}/User/settings.json"
fi

touch "${DATA_HOME}/.gitconfig" "${DATA_HOME}/.zsh_history"
chmod 0600 "${DATA_HOME}/.zsh_history"

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
export HASS_TOKEN="${SUPERVISOR_TOKEN:-}"

bashio::log.info "Starting Studio Code Server on the Home Assistant Ingress"
bashio::log.info "Workspace: ${workspace_path}"
bashio::log.info "Codex CLI: $(codex --version)"
bashio::log.info "Run 'codex login --device-auth' once from the integrated terminal"
bashio::log.warning "The bundled Codex IDE extension is experimental under code-server; use the Codex CLI if it does not load"

cd "${workspace_path}"
exec code-server \
  --host 0.0.0.0 \
  --port 1337 \
  --auth none \
  --disable-telemetry \
  --disable-update-check \
  --user-data-dir "${USER_DATA}" \
  --extensions-dir "${USER_DATA}/extensions" \
  "${workspace_path}"
