#!/bin/bash

DATA_DIR="${DATA_DIR:-/data}"
JOBS_FILE="$DATA_DIR/jobs.json"
CONFIG_FILE="$DATA_DIR/config.json"

send_notification() {
    JOB_NAME="$1"; STATUS="$2"; LOG_CONTENT="$3"; FORCE_SEND="$4"
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "[EMAIL] Configuration introuvable: $CONFIG_FILE"
        return 1
    fi

    CONF=$(cat "$CONFIG_FILE")

    if [ "$(echo "$CONF" | jq -r '.email_enabled // false')" != "true" ] && [ "$FORCE_SEND" != "force" ]; then
        echo "[EMAIL] Notifications email désactivées."
        return 0
    fi

    # Variables Gmail / SMTP
    SMTP_HOST=$(echo "$CONF" | jq -r '.smtp_host // ""')
    SMTP_PORT=$(echo "$CONF" | jq -r '.smtp_port // ""')
    SMTP_USER=$(echo "$CONF" | jq -r '.smtp_user // ""')
    SMTP_PASS=$(echo "$CONF" | jq -r '.smtp_pass // ""')
    MAIL_TO=$(echo "$CONF" | jq -r '.mail_to // ""')
    MAIL_FROM=$(echo "$CONF" | jq -r '.mail_from // ""')

    # Options de sécurité (Auth, TLS, STARTTLS)
    AUTH=$(echo "$CONF" | jq -r '.smtp_auth // "on"')
    TLS=$(echo "$CONF" | jq -r '.smtp_tls // "on"')
    STARTTLS=$(echo "$CONF" | jq -r '.smtp_starttls // "on"')

    if [ "$STARTTLS" = "on" ] && [ "$TLS" != "on" ]; then
        echo "[EMAIL] STARTTLS est activé: activation automatique de TLS pour msmtp."
        TLS="on"
    fi

    [ -z "$MAIL_FROM" ] && MAIL_FROM="$SMTP_USER"

    if [ -z "$SMTP_HOST" ] || [ -z "$SMTP_PORT" ] || [ -z "$MAIL_TO" ] || [ -z "$MAIL_FROM" ]; then
        echo "[EMAIL] Configuration incomplète: smtp_host, smtp_port, mail_from et mail_to sont obligatoires."
        return 1
    fi

    if [ "$AUTH" = "on" ] && { [ -z "$SMTP_USER" ] || [ -z "$SMTP_PASS" ]; }; then
        echo "[EMAIL] Configuration incomplète: smtp_user et smtp_pass sont obligatoires quand l'authentification est activée."
        return 1
    fi

    echo "[EMAIL] Tentative d'envoi via $SMTP_HOST:$SMTP_PORT vers $MAIL_TO..."

    MSMTP_ARGS=(
        --host="$SMTP_HOST"
        --port="$SMTP_PORT"
        --auth="$AUTH"
        --tls="$TLS"
        --tls-starttls="$STARTTLS"
        --tls-certcheck=off
        --from="$MAIL_FROM"
    )

    PASS_FILE=""
    if [ "$AUTH" = "on" ]; then
        PASS_FILE=$(mktemp)
        chmod 600 "$PASS_FILE"
        printf '%s' "$SMTP_PASS" > "$PASS_FILE"
        MSMTP_ARGS+=(--user="$SMTP_USER" --passwordeval="cat $PASS_FILE")
    fi

    MSMTP_OUTPUT=$({
      echo "Subject: Rsync Manager: $STATUS [$JOB_NAME]"
      echo "To: $MAIL_TO"
      echo "From: $MAIL_FROM"
      echo "Content-Type: text/plain; charset=UTF-8"
      echo ""
      echo "Rapport d'exécution : $JOB_NAME"
      echo "Statut : $STATUS"
      echo "--------------------------------------"
      echo "$LOG_CONTENT"
    } | msmtp "${MSMTP_ARGS[@]}" "$MAIL_TO" 2>&1)
    MSMTP_STATUS=$?

    [ -n "$PASS_FILE" ] && rm -f "$PASS_FILE"

    if [ "$MSMTP_STATUS" -eq 0 ]; then
        echo "[EMAIL] Message envoyé avec succès."
        return 0
    fi

    echo "[EMAIL] Échec de l'envoi msmtp (code $MSMTP_STATUS)."
    [ -n "$MSMTP_OUTPUT" ] && echo "$MSMTP_OUTPUT"
    return "$MSMTP_STATUS"
}

run_job() {
    INDEX="$1"; MODE="$2"; LOG_TEMP="/tmp/rsync.log"
    JOB=$(jq -c ".[$INDEX]" "$JOBS_FILE")
    NAME=$(echo "$JOB" | jq -r '.name')

    echo "--- DÉMARRAGE : $NAME (Mode $MODE) ---" > /proc/1/fd/1

    prepare_path() {
        SIDE_NAME="$1"
        SIDE="$2"
        RESULT_VAR="$3"
        if [ "$(echo "$SIDE" | jq -r '.type')" = "cifs" ]; then
            HOST=$(echo "$SIDE" | jq -r '.host // ""')
            SHARE=$(echo "$SIDE" | jq -r '.share // ""')
            SUBPATH=$(echo "$SIDE" | jq -r '.subpath // ""')
            OLD_PATH=$(echo "$SIDE" | jq -r '.path // ""')
            USER=$(echo "$SIDE" | jq -r '.user // ""')
            PASS=$(echo "$SIDE" | jq -r '.pass // ""')
            DOMAIN=$(echo "$SIDE" | jq -r '.domain // ""')
            VERS=$(echo "$SIDE" | jq -r '.vers // "3.0"')
            SEC=$(echo "$SIDE" | jq -r '.sec // "ntlmssp"')
            EXTRA_OPTIONS=$(echo "$SIDE" | jq -r '.options // "noserverino,nounix"')

            USER="${USER%$'\r'}"
            PASS="${PASS%$'\r'}"
            DOMAIN="${DOMAIN%$'\r'}"
            VERS="${VERS%$'\r'}"
            SEC="${SEC%$'\r'}"
            EXTRA_OPTIONS="${EXTRA_OPTIONS%$'\r'}"

            if [ -n "$HOST" ] && [ -n "$SHARE" ]; then
                HOST="${HOST#//}"
                HOST="${HOST#\\\\}"
                HOST="${HOST%%/*}"
                SHARE="${SHARE#/}"
                SHARE="${SHARE#\\}"
                SHARE="${SHARE%/}"
                SHARE="${SHARE%\\}"
                if [[ "$SHARE" == *"/"* ]]; then
                    SHARE_PATH="$SHARE"
                    if [[ "$SHARE_PATH" == "$HOST/"* ]]; then
                        SHARE_PATH="${SHARE_PATH#"$HOST/"}"
                    fi
                    SHARE="${SHARE_PATH%%/*}"
                    EXTRA_PATH="${SHARE_PATH#*/}"
                    [ "$EXTRA_PATH" != "$SHARE_PATH" ] && SUBPATH="${SUBPATH:-$EXTRA_PATH}"
                fi
                REMOTE="//$HOST/$SHARE"
            else
                UNC="${OLD_PATH#//}"
                HOST="${UNC%%/*}"
                REST="${UNC#*/}"
                SHARE="${REST%%/*}"
                SUBPATH="${SUBPATH:-${REST#*/}}"
                [ "$SUBPATH" = "$REST" ] && SUBPATH=""
                REMOTE="//$HOST/$SHARE"
            fi

            if [ -z "$REMOTE" ] || [ -z "$USER" ]; then
                echo "[CIFS] Configuration $SIDE_NAME incomplète: adresse/partage et login sont obligatoires." > /proc/1/fd/1
                return 1
            fi

            MNT="/mnt/rsync_${INDEX}_${SIDE_NAME}_$(date +%s)"
            CREDS=$(mktemp)
            chmod 600 "$CREDS"
            {
                printf 'username=%s\n' "$USER"
                printf 'password=%s\n' "$PASS"
                [ -n "$DOMAIN" ] && printf 'domain=%s\n' "$DOMAIN"
            } > "$CREDS"

            mkdir -p "$MNT"
            OPTS="credentials=$CREDS,iocharset=utf8,vers=$VERS,noperm"
            [ -n "$SEC" ] && OPTS="$OPTS,sec=$SEC"
            [ -n "$EXTRA_OPTIONS" ] && OPTS="$OPTS,$EXTRA_OPTIONS"
            echo "[CIFS] Montage $SIDE_NAME: $REMOTE -> $MNT (vers=$VERS${SEC:+, sec=$SEC}${DOMAIN:+, domain=$DOMAIN}, noperm${EXTRA_OPTIONS:+, options=$EXTRA_OPTIONS})" > /proc/1/fd/1
            MOUNT_LOG=$(mktemp)
            mount -v -t cifs "$REMOTE" "$MNT" -o "$OPTS" > "$MOUNT_LOG" 2>&1
            MOUNT_STATUS=$?
            if [ "$MOUNT_STATUS" -ne 0 ]; then
                cat "$MOUNT_LOG" > /proc/1/fd/1
                echo "[CIFS] Échec montage $SIDE_NAME." > /proc/1/fd/1
                rm -f "$CREDS"
                rm -f "$MOUNT_LOG"
                rmdir "$MNT" 2>/dev/null
                return 1
            fi
            rm -f "$MOUNT_LOG"
            rm -f "$CREDS"
            SUBPATH="${SUBPATH#/}"
            SUBPATH="${SUBPATH%/}"
            if [ -n "$SUBPATH" ]; then
                printf -v "$RESULT_VAR" '%s' "$MNT/$SUBPATH"
            else
                printf -v "$RESULT_VAR" '%s' "$MNT"
            fi
        else
            printf -v "$RESULT_VAR" '%s' "$(echo "$SIDE" | jq -r '.path // ""')"
        fi
    }

    SRC_MNT=""
    DST_MNT=""
    prepare_path "source" "$(echo "$JOB" | jq -c '.source')" SRC_MNT
    SRC_STATUS=$?
    prepare_path "destination" "$(echo "$JOB" | jq -c '.target')" DST_MNT
    DST_STATUS=$?

    if [ "$SRC_STATUS" -ne 0 ] || [ "$DST_STATUS" -ne 0 ] || [ -z "$SRC_MNT" ] || [ -z "$DST_MNT" ]; then
        STATUS="ERREUR"; echo "Échec montage réseau." > "$LOG_TEMP"
    else
        OPTS="-avh --delete"; [ "$MODE" = "dry" ] && OPTS="$OPTS --dry-run"
        rsync $OPTS "$SRC_MNT/" "$DST_MNT/" > "$LOG_TEMP" 2>&1
        [ $? -eq 0 ] && STATUS="SUCCÈS" || STATUS="ÉCHEC"
    fi

    cat "$LOG_TEMP" > /proc/1/fd/1
    [ "$MODE" = "run" ] && send_notification "$NAME" "$STATUS" "$(cat $LOG_TEMP)"

    for MNT in /mnt/rsync_${INDEX}_source_* /mnt/rsync_${INDEX}_destination_*; do
        [ -d "$MNT" ] || continue
        umount "$MNT" 2>/dev/null || true
        rmdir "$MNT" 2>/dev/null || true
    done
}

case "$1" in
    list) cat "$JOBS_FILE" ;;
    save) cat > "$JOBS_FILE" ;;
    test_email) send_notification "TEST" "OK" "Vérification configuration SMTP." "force" ;;
    run|dry) run_job "$2" "$1" ;;
esac
