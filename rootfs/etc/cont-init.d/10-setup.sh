#!/usr/bin/with-contenv bashio
set -e

# Dossiers de base
mkdir -p /data
mkdir -p /mnt
chmod 755 /mnt

# 1. Initialisation du fichier de Configuration (JSON)
# Remplace l'ancien email.conf
DEFAULT_CONFIG=$(mktemp)
cat <<EOF > "$DEFAULT_CONFIG"
{
    "email_enabled": false,
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "mail_from": "rsync-manager@ha.local",
    "mail_to": "",
    "smtp_user": "",
    "smtp_pass": "",
    "smtp_auth": "on",
    "smtp_tls": "on",
    "smtp_starttls": "on"
}
EOF

if [ ! -f /data/config.json ]; then
    bashio::log.info "Création de la configuration par défaut (/data/config.json)..."
    cat "$DEFAULT_CONFIG" > /data/config.json
    chmod 666 /data/config.json
elif jq -e . /data/config.json >/dev/null 2>&1; then
    bashio::log.info "Vérification des clés de configuration (/data/config.json)..."
    MERGED_CONFIG=$(mktemp)
    jq -s '.[0] * .[1]' "$DEFAULT_CONFIG" /data/config.json > "$MERGED_CONFIG"
    cat "$MERGED_CONFIG" > /data/config.json
    chmod 666 /data/config.json
    rm -f "$MERGED_CONFIG"
else
    bashio::log.warning "Configuration invalide, remplacement par la configuration par défaut."
    cat "$DEFAULT_CONFIG" > /data/config.json
    chmod 666 /data/config.json
fi
rm -f "$DEFAULT_CONFIG"

# 2. Initialisation du fichier des Jobs (JSON)
# Remplace l'ancien jobs.txt
if [ ! -f /data/jobs.json ]; then
    bashio::log.info "Initialisation de la liste des jobs (/data/jobs.json)..."
    echo '[]' > /data/jobs.json
    chmod 666 /data/jobs.json
fi

# 3. Reconstruction du crontab système au démarrage
/usr/local/bin/rsync_cron.sh

bashio::log.info "Setup terminé."
