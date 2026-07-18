#!/usr/bin/with-contenv bashio
set -euo pipefail

readonly CONFIG_PATH="/config/config.yaml"
readonly DEFAULT_CONFIG="/usr/share/gatus/config.example.yaml"

if [[ ! -f "${CONFIG_PATH}" ]]; then
  install -m 0644 "${DEFAULT_CONFIG}" "${CONFIG_PATH}"
  bashio::log.notice "Created initial Gatus configuration at ${CONFIG_PATH}"
fi

if [[ ! -r "${CONFIG_PATH}" ]]; then
  bashio::log.fatal "Gatus configuration is not readable: ${CONFIG_PATH}"
  exit 1
fi

required_options=(
  sms_user
  sms_password
  email_from
  email_username
  email_password
  email_host
  email_port
  email_to
)

missing_options=()
for option in "${required_options[@]}"; do
  if ! bashio::config.has_value "${option}"; then
    missing_options+=("${option}")
  fi
done

if (( ${#missing_options[@]} > 0 )); then
  bashio::log.fatal "Missing required app options: ${missing_options[*]}"
  exit 1
fi

email_port="$(bashio::config 'email_port')"
if [[ ! "${email_port}" =~ ^[0-9]+$ ]] || (( email_port < 1 || email_port > 65535 )); then
  bashio::log.fatal "email_port must be between 1 and 65535"
  exit 1
fi

export GATUS_SMS_USER
export GATUS_SMS_PASSWORD
export GATUS_EMAIL_FROM
export GATUS_EMAIL_USERNAME
export GATUS_EMAIL_PASSWORD
export GATUS_EMAIL_HOST
export GATUS_EMAIL_PORT="${email_port}"
export GATUS_EMAIL_TO
export GATUS_LOG_LEVEL
export GATUS_CONFIG_PATH="${CONFIG_PATH}"

GATUS_SMS_USER="$(bashio::config 'sms_user')"
GATUS_SMS_PASSWORD="$(bashio::config 'sms_password')"
GATUS_EMAIL_FROM="$(bashio::config 'email_from')"
GATUS_EMAIL_USERNAME="$(bashio::config 'email_username')"
GATUS_EMAIL_PASSWORD="$(bashio::config 'email_password')"
GATUS_EMAIL_HOST="$(bashio::config 'email_host')"
GATUS_EMAIL_TO="$(bashio::config 'email_to')"
GATUS_LOG_LEVEL="$(bashio::config 'log_level')"

install -d -m 0750 -o gatus -g gatus /data/gatus

bashio::log.info "Starting Gatus as an unprivileged user"
exec su-exec gatus:gatus /usr/local/bin/gatus
