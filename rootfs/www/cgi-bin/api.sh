#!/bin/bash
echo "Content-type: application/json"
echo ""

DATA_DIR="${DATA_DIR:-/data}"
CONFIG_FILE="$DATA_DIR/config.json"
JOBS_FILE="$DATA_DIR/jobs.json"

ACTION=$(echo "$QUERY_STRING" | grep -oE "action=[a-z_]+" | cut -d= -f2)
INDEX=$(echo "$QUERY_STRING" | grep -oE "index=[0-9]+" | cut -d= -f2)

log_api() {
    echo "[API] $*" > /proc/1/fd/1
}

default_config() {
    cat <<'EOF'
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
}

ensure_config() {
    mkdir -p "$DATA_DIR"

    if [ ! -s "$CONFIG_FILE" ] || ! jq -e . "$CONFIG_FILE" >/dev/null 2>&1; then
        default_config > "$CONFIG_FILE"
        chmod 666 "$CONFIG_FILE"
        return
    fi

    DEFAULT_TMP=$(mktemp)
    MERGED_TMP=$(mktemp)
    default_config > "$DEFAULT_TMP"

    if jq -s '.[0] * .[1]' "$DEFAULT_TMP" "$CONFIG_FILE" > "$MERGED_TMP"; then
        cat "$MERGED_TMP" > "$CONFIG_FILE"
        chmod 666 "$CONFIG_FILE"
    fi

    rm -f "$DEFAULT_TMP" "$MERGED_TMP"
}

save_config() {
    BODY_TMP=$(mktemp)
    DEFAULT_TMP=$(mktemp)
    MERGED_TMP=$(mktemp)

    cat > "$BODY_TMP"
    default_config > "$DEFAULT_TMP"
    log_api "save_config reçu ($(wc -c < "$BODY_TMP") octets)"

    if ! jq -e . "$BODY_TMP" >/dev/null 2>&1; then
        log_api "save_config refusé: JSON invalide"
        rm -f "$BODY_TMP" "$DEFAULT_TMP" "$MERGED_TMP"
        echo '{"status":"error","error":"Configuration JSON invalide"}'
        return 1
    fi

    if jq -s '.[0] * .[1]' "$DEFAULT_TMP" "$BODY_TMP" > "$MERGED_TMP"; then
        cat "$MERGED_TMP" > "$CONFIG_FILE"
        chmod 666 "$CONFIG_FILE"
        log_api "save_config sauvegardé dans $CONFIG_FILE avec les clés: $(jq -r 'keys | join(",")' "$CONFIG_FILE")"
        echo '{"status":"ok"}'
    else
        log_api "save_config échec jq"
        echo '{"status":"error","error":"Impossible de sauvegarder la configuration"}'
        rm -f "$BODY_TMP" "$DEFAULT_TMP" "$MERGED_TMP"
        return 1
    fi

    rm -f "$BODY_TMP" "$DEFAULT_TMP" "$MERGED_TMP"
}

save_jobs() {
    BODY_TMP=$(mktemp)
    FORMATTED_TMP=$(mktemp)

    cat > "$BODY_TMP"
    log_api "save_jobs reçu ($(wc -c < "$BODY_TMP") octets)"

    if ! jq -e 'type == "array"' "$BODY_TMP" >/dev/null 2>&1; then
        log_api "save_jobs refusé: JSON invalide ou non-tableau"
        rm -f "$BODY_TMP" "$FORMATTED_TMP"
        echo '{"status":"error","error":"Jobs JSON invalide"}'
        return 1
    fi

    if jq . "$BODY_TMP" > "$FORMATTED_TMP"; then
        cat "$FORMATTED_TMP" > "$JOBS_FILE"
        chmod 666 "$JOBS_FILE"
        log_api "save_jobs sauvegardé dans $JOBS_FILE"
        if /usr/local/bin/rsync_cron.sh; then
            log_api "crontab régénéré après sauvegarde des jobs"
        else
            log_api "échec régénération crontab après sauvegarde des jobs"
            echo '{"status":"error","error":"Jobs sauvegardés, mais impossible de régénérer le cron"}'
            rm -f "$BODY_TMP" "$FORMATTED_TMP"
            return 1
        fi
        echo '{"status":"ok"}'
    else
        log_api "save_jobs échec jq"
        echo '{"status":"error","error":"Impossible de sauvegarder les jobs"}'
        rm -f "$BODY_TMP" "$FORMATTED_TMP"
        return 1
    fi

    rm -f "$BODY_TMP" "$FORMATTED_TMP"
}

test_email() {
    log_api "test_email demandé"
    OUTPUT=$(/usr/local/bin/rsync_manager.sh test_email 2>&1)
    STATUS=$?

    printf '%s\n' "$OUTPUT" > /proc/1/fd/1

    if [ "$STATUS" -eq 0 ]; then
        echo '{"status":"sent"}'
    else
        jq -n --arg error "$OUTPUT" '{"status":"error","error":$error}'
    fi
}

queue_job() {
    QUEUE_DIR="/tmp/rsync_manager_queue"
    mkdir -p "$QUEUE_DIR"

    if ! printf '%s' "$INDEX" | grep -Eq '^[0-9]+$'; then
        echo '{"status":"error","error":"Index job invalide"}'
        return 1
    fi

    JOB_TMP=$(mktemp "$QUEUE_DIR/.job.XXXXXX")
    printf '%s %s\n' "$ACTION" "$INDEX" > "$JOB_TMP"
    mv "$JOB_TMP" "$QUEUE_DIR/$(date +%s%N)_${ACTION}_${INDEX}.job"
    log_api "job mis en file: action=$ACTION index=$INDEX"
    echo '{"status":"started"}'
}

# Redirection directe vers le journal de l'addon (fd/1)
log_api "action=$ACTION method=${REQUEST_METHOD:-GET} query=$QUERY_STRING"
case "$ACTION" in
    list_jobs)   /usr/local/bin/rsync_manager.sh list ;;
    save_jobs)   save_jobs ;;
    get_config)  ensure_config; cat "$CONFIG_FILE" ;;
    save_config) save_config ;;
    test_email)  ensure_config; test_email ;;
    run|dry)     queue_job ;;
    *)           echo '{"status":"error","error":"Action inconnue"}' ;;
esac
