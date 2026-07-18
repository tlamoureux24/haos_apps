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

read_optional_option() {
  local value
  value="$(bashio::config "$1")"
  if [[ "${value}" == "null" ]]; then
    value=""
  fi
  printf '%s' "${value}"
}

email_port="$(read_optional_option 'email_port')"
if [[ -n "${email_port}" ]] \
  && { [[ ! "${email_port}" =~ ^[0-9]+$ ]] \
    || (( email_port < 1 || email_port > 65535 )); }; then
  bashio::log.fatal "email_port must be between 1 and 65535"
  exit 1
fi

GATUS_SMS_USER="$(read_optional_option 'sms_user')"
GATUS_SMS_PASSWORD="$(read_optional_option 'sms_password')"
GATUS_EMAIL_FROM="$(read_optional_option 'email_from')"
GATUS_EMAIL_USERNAME="$(read_optional_option 'email_username')"
GATUS_EMAIL_PASSWORD="$(read_optional_option 'email_password')"
GATUS_EMAIL_HOST="$(read_optional_option 'email_host')"
GATUS_EMAIL_PORT="${email_port}"
GATUS_EMAIL_TO="$(read_optional_option 'email_to')"
GATUS_LOG_LEVEL="$(read_optional_option 'log_level')"
GATUS_LOG_LEVEL="${GATUS_LOG_LEVEL:-INFO}"
GATUS_CONFIG_PATH="${CONFIG_PATH}"

export GATUS_SMS_USER
export GATUS_SMS_PASSWORD
export GATUS_EMAIL_FROM
export GATUS_EMAIL_USERNAME
export GATUS_EMAIL_PASSWORD
export GATUS_EMAIL_HOST
export GATUS_EMAIL_PORT
export GATUS_EMAIL_TO
export GATUS_LOG_LEVEL
export GATUS_CONFIG_PATH

install -d -m 0750 -o gatus -g gatus /data/gatus

bashio::log.info "Starting Gatus as an unprivileged user"
exec su-exec gatus:gatus /usr/local/bin/gatus
