#!/bin/bash

DATA_DIR="${DATA_DIR:-/data}"
JOBS_FILE="$DATA_DIR/jobs.json"
CONFIG_FILE="$DATA_DIR/config.json"
STATUS_FILE="$DATA_DIR/status.json"
LOG_DIR="$DATA_DIR/logs"

generate_job_id() {
    printf 'job_%s_%s' "$(date +%s%N)" "$RANDOM"
}

normalize_jobs_file() {
    local INPUT_FILE="$1"
    local OUTPUT_FILE="$2"
    local NORMALIZED_TMP
    local SEEN_IDS_TMP
    local COUNT
    local JOB
    local JOB_ID
    local UPDATED_TMP
    local STATUS

    NORMALIZED_TMP=$(mktemp)
    SEEN_IDS_TMP=$(mktemp)

    echo '[]' > "$NORMALIZED_TMP"
    : > "$SEEN_IDS_TMP"

    if [ ! -f "$INPUT_FILE" ] || ! jq -e 'type == "array"' "$INPUT_FILE" >/dev/null 2>&1; then
        rm -f "$NORMALIZED_TMP" "$SEEN_IDS_TMP"
        return 1
    fi

    COUNT=$(jq '. | length' "$INPUT_FILE")
    if [ "$COUNT" -gt 0 ]; then
        for i in $(seq 0 $((COUNT - 1))); do
            JOB=$(jq -c ".[$i]" "$INPUT_FILE")
            JOB_ID=$(echo "$JOB" | jq -r '.id // ""')

            if ! printf '%s' "$JOB_ID" | grep -Eq '^job_[A-Za-z0-9_-]+$' || grep -Fxq "$JOB_ID" "$SEEN_IDS_TMP"; then
                while true; do
                    JOB_ID=$(generate_job_id)
                    if ! grep -Fxq "$JOB_ID" "$SEEN_IDS_TMP"; then
                        break
                    fi
                done
            fi

            printf '%s\n' "$JOB_ID" >> "$SEEN_IDS_TMP"
            UPDATED_TMP=$(mktemp)
            jq --argjson job "$(echo "$JOB" | jq --arg id "$JOB_ID" 'del(
                .rsync_inplace,
                .rsync_smb_permissions,
                .rsync_repair_blocked,
                .source.vers,
                .source.sec,
                .source.options,
                .target.vers,
                .target.sec,
                .target.options
            ) + {
                id: $id,
                enabled: (if has("enabled") then .enabled else true end),
                excludes: (if (.excludes | type) == "array" then .excludes else [] end)
            }')" '. + [$job]' "$NORMALIZED_TMP" > "$UPDATED_TMP"
            mv "$UPDATED_TMP" "$NORMALIZED_TMP"
        done
    fi

    jq . "$NORMALIZED_TMP" > "$OUTPUT_FILE"
    STATUS=$?
    rm -f "$NORMALIZED_TMP" "$SEEN_IDS_TMP"
    return "$STATUS"
}

ensure_jobs_file() {
    local NORMALIZED_TMP

    mkdir -p "$DATA_DIR"

    if [ ! -f "$JOBS_FILE" ]; then
        echo '[]' > "$JOBS_FILE"
        chmod 666 "$JOBS_FILE"
        return 0
    fi

    NORMALIZED_TMP=$(mktemp)
    if normalize_jobs_file "$JOBS_FILE" "$NORMALIZED_TMP"; then
        cat "$NORMALIZED_TMP" > "$JOBS_FILE"
        chmod 666 "$JOBS_FILE"
        rm -f "$NORMALIZED_TMP"
        return 0
    fi

    rm -f "$NORMALIZED_TMP"
    return 1
}

ensure_status_storage() {
    mkdir -p "$DATA_DIR" "$LOG_DIR"

    if [ ! -f "$STATUS_FILE" ] || ! jq -e 'type == "object"' "$STATUS_FILE" >/dev/null 2>&1; then
        echo '{}' > "$STATUS_FILE"
        chmod 666 "$STATUS_FILE"
    fi
}

log_line() {
    local MESSAGE="$1"
    local TARGET_LOG="${2:-}"

    if [ -n "$TARGET_LOG" ]; then
        echo "$MESSAGE" | tee -a "$TARGET_LOG" > /proc/1/fd/1
    else
        echo "$MESSAGE" > /proc/1/fd/1
    fi
}

safe_cifs_options_for_log() {
    local OPTIONS="$1"
    printf '%s' "$OPTIONS" | sed -E 's#credentials=[^,]*#credentials=<masque>#g'
}

join_shell_args_for_log() {
    printf '%q ' "$@"
}

update_job_status() {
    local JOB_ID="$1"
    local STATUS_KEY="$2"
    local LABEL="$3"
    local MODE="$4"
    local TRIGGER="$5"
    local STARTED_AT="$6"
    local FINISHED_AT="$7"
    local DURATION_SECONDS="$8"
    local EXIT_CODE="$9"
    local MESSAGE="${10}"
    local LOG_FILE="${11}"
    local RSYNC_SENT_LINE="${12}"
    local RSYNC_TOTAL_LINE="${13}"
    local BYTES_SENT=""
    local BYTES_RECEIVED=""
    local TOTAL_SIZE=""
    local SPEEDUP=""
    local STATUS_TMP

    ensure_status_storage

    if [ -n "$RSYNC_SENT_LINE" ]; then
        BYTES_SENT=$(printf '%s\n' "$RSYNC_SENT_LINE" | awk '{print $2 " " $3}')
        BYTES_RECEIVED=$(printf '%s\n' "$RSYNC_SENT_LINE" | awk '{print $5 " " $6}')
    fi

    if [ -n "$RSYNC_TOTAL_LINE" ]; then
        TOTAL_SIZE=$(printf '%s\n' "$RSYNC_TOTAL_LINE" | awk '{print $4}')
        SPEEDUP=$(printf '%s\n' "$RSYNC_TOTAL_LINE" | awk '{print $7}')
    fi

    STATUS_TMP=$(mktemp)
    if jq \
        --arg id "$JOB_ID" \
        --arg status "$STATUS_KEY" \
        --arg label "$LABEL" \
        --arg mode "$MODE" \
        --arg trigger "$TRIGGER" \
        --arg started_at "$STARTED_AT" \
        --arg finished_at "$FINISHED_AT" \
        --arg message "$MESSAGE" \
        --arg log_file "$LOG_FILE" \
        --arg bytes_sent "$BYTES_SENT" \
        --arg bytes_received "$BYTES_RECEIVED" \
        --arg total_size "$TOTAL_SIZE" \
        --arg speedup "$SPEEDUP" \
        --argjson duration_seconds "$DURATION_SECONDS" \
        --argjson exit_code "$EXIT_CODE" \
        '.[$id] = {
            status: $status,
            label: $label,
            mode: $mode,
            trigger: $trigger,
            started_at: $started_at,
            finished_at: $finished_at,
            duration_seconds: $duration_seconds,
            exit_code: $exit_code,
            message: $message,
            bytes_sent: $bytes_sent,
            bytes_received: $bytes_received,
            total_size: $total_size,
            speedup: $speedup,
            log_file: $log_file
        }' "$STATUS_FILE" > "$STATUS_TMP"; then
        cat "$STATUS_TMP" > "$STATUS_FILE"
        chmod 666 "$STATUS_FILE"
    fi

    rm -f "$STATUS_TMP"
}

finish_job_log() {
    local JOB_ID="$1"
    local STATUS_KEY="$2"
    local LABEL="$3"
    local MODE="$4"
    local TRIGGER="$5"
    local STARTED_AT="$6"
    local START_EPOCH="$7"
    local EXIT_CODE="$8"
    local MESSAGE="$9"
    local LOG_TEMP="${10}"
    local EXEC_LOG_TEMP="${11}"
    local JOB_LOG_FILE="$LOG_DIR/${JOB_ID}.log"
    local END_EPOCH
    local FINISHED_AT
    local DURATION_SECONDS
    local RSYNC_SENT_LINE
    local RSYNC_TOTAL_LINE
    local EXCLUDES_FILE
    local EXCLUDES_COUNT

    END_EPOCH=$(date +%s)
    FINISHED_AT=$(date -Iseconds)
    DURATION_SECONDS=$((END_EPOCH - START_EPOCH))
    {
        echo "Fin : $FINISHED_AT"
        echo "Durée : ${DURATION_SECONDS}s"
        echo "Statut : $LABEL"
    } | tee -a "$LOG_TEMP" >> "$EXEC_LOG_TEMP"

    cat "$EXEC_LOG_TEMP" > /proc/1/fd/1
    cp "$LOG_TEMP" "$JOB_LOG_FILE"
    chmod 666 "$JOB_LOG_FILE"

    RSYNC_SENT_LINE=$(grep -E '^sent .* bytes .* received .* bytes' "$LOG_TEMP" | tail -n 1 || true)
    RSYNC_TOTAL_LINE=$(grep -E '^total size is .* speedup is ' "$LOG_TEMP" | tail -n 1 || true)
    update_job_status "$JOB_ID" "$STATUS_KEY" "$LABEL" "$MODE" "$TRIGGER" "$STARTED_AT" "$FINISHED_AT" "$DURATION_SECONDS" "$EXIT_CODE" "$MESSAGE" "$JOB_LOG_FILE" "$RSYNC_SENT_LINE" "$RSYNC_TOTAL_LINE"
}

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
    local JOB_ID="$1"
    local MODE="$2"
    local TRIGGER="${3:-manual}"
    local LOG_TEMP="/tmp/rsync.log"
    local EXEC_LOG_TEMP
    local JOB_LOG_FILE="$LOG_DIR/${JOB_ID}.log"
    local JOB
    local NAME
    local SRC_MNT
    local DST_MNT
    local SRC_STATUS
    local DST_STATUS
    local STATUS
    local TARGET_TYPE
    local -a RSYNC_OPTS
    local MNT
    local START_EPOCH
    local END_EPOCH
    local STARTED_AT
    local FINISHED_AT
    local DURATION_SECONDS
    local EXIT_CODE
    local STATUS_KEY
    local LABEL
    local MESSAGE
    local RSYNC_SENT_LINE
    local RSYNC_TOTAL_LINE

    ensure_jobs_file || {
        echo "[RUN] Fichier jobs invalide: $JOBS_FILE" > /proc/1/fd/1
        return 1
    }
    ensure_status_storage

    JOB=$(jq -c --arg id "$JOB_ID" '.[] | select(.id == $id)' "$JOBS_FILE")

    if [ -z "$JOB" ]; then
        echo "[RUN] Job introuvable: id=$JOB_ID" > /proc/1/fd/1
        return 1
    fi

    NAME=$(echo "$JOB" | jq -r '.name')

    START_EPOCH=$(date +%s)
    STARTED_AT=$(date -Iseconds)
    EXEC_LOG_TEMP=$(mktemp)
    EXCLUDES_FILE=$(mktemp)
    : > "$LOG_TEMP"
    {
        echo "--- DÉMARRAGE : $NAME (id $JOB_ID, Mode $MODE, Déclenchement $TRIGGER) ---"
        echo "Début : $STARTED_AT"
    } | tee -a "$LOG_TEMP" > /proc/1/fd/1

    prepare_path() {
        local SIDE_NAME="$1"
        local SIDE="$2"
        local RESULT_VAR="$3"
        local HOST
        local SHARE
        local SUBPATH
        local OLD_PATH
        local USER
        local PASS
        local DOMAIN
        local VERS
        local SEC
        local EXTRA_OPTIONS
        local SHARE_PATH
        local EXTRA_PATH
        local UNC
        local REST
        local REMOTE
        local MNT
        local CREDS
        local OPTS
        local SAFE_OPTS
        local MOUNT_LOG
        local MOUNT_STATUS

        if [ "$(echo "$SIDE" | jq -r '.type')" = "cifs" ]; then
            HOST=$(echo "$SIDE" | jq -r '.host // ""')
            SHARE=$(echo "$SIDE" | jq -r '.share // ""')
            SUBPATH=$(echo "$SIDE" | jq -r '.subpath // ""')
            OLD_PATH=$(echo "$SIDE" | jq -r '.path // ""')
            USER=$(echo "$SIDE" | jq -r '.user // ""')
            PASS=$(echo "$SIDE" | jq -r '.pass // ""')
            DOMAIN=$(echo "$SIDE" | jq -r '.domain // ""')
            VERS="3.0"
            SEC="ntlmssp"
            EXTRA_OPTIONS="noserverino,nounix"

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

            MNT="/mnt/rsync_${JOB_ID}_${SIDE_NAME}_$(date +%s)"
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
            SAFE_OPTS=$(safe_cifs_options_for_log "$OPTS")
            log_line "[CIFS] Montage $SIDE_NAME: $REMOTE -> $MNT" "$LOG_TEMP"
            log_line "[CIFS] Options montage $SIDE_NAME: $SAFE_OPTS${DOMAIN:+, domain=$DOMAIN}" "$LOG_TEMP"
            MOUNT_LOG=$(mktemp)
            mount -v -t cifs "$REMOTE" "$MNT" -o "$OPTS" > "$MOUNT_LOG" 2>&1
            MOUNT_STATUS=$?
            if [ "$MOUNT_STATUS" -ne 0 ]; then
                cat "$MOUNT_LOG" | tee -a "$LOG_TEMP" > /proc/1/fd/1
                echo "[CIFS] Échec montage $SIDE_NAME." | tee -a "$LOG_TEMP" > /proc/1/fd/1
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
        STATUS="ERREUR"
        STATUS_KEY="mount_error"
        LABEL="Erreur montage"
        MESSAGE="Échec montage réseau."
        EXIT_CODE=1
        echo "$MESSAGE" | tee -a "$LOG_TEMP" > "$EXEC_LOG_TEMP"
    else
        RSYNC_OPTS=(-a -v -h --delete)
        [ "$MODE" = "dry" ] && RSYNC_OPTS+=(--dry-run)

        TARGET_TYPE=$(echo "$JOB" | jq -r '.target.type // "local"')
        if [ "$TARGET_TYPE" = "cifs" ]; then
            RSYNC_OPTS+=(--inplace --no-perms --no-owner --no-group --chmod=ugo=rwX)
        fi

        jq -r '.excludes // [] | .[]' <<< "$JOB" | sed '/^[[:space:]]*$/d' > "$EXCLUDES_FILE"
        EXCLUDES_COUNT=$(wc -l < "$EXCLUDES_FILE")
        if [ "$EXCLUDES_COUNT" -gt 0 ]; then
            echo "[RSYNC] Exclusions actives: $EXCLUDES_COUNT règle(s)." | tee -a "$LOG_TEMP" > /proc/1/fd/1
            RSYNC_OPTS+=(--exclude-from="$EXCLUDES_FILE")
        fi
        if [ "$TARGET_TYPE" = "cifs" ]; then
            log_line "[RSYNC] Profil SMB/CIFS actif." "$LOG_TEMP"
        fi
        log_line "[RSYNC] Options appliquées: $(join_shell_args_for_log "${RSYNC_OPTS[@]}")" "$LOG_TEMP"
        rsync "${RSYNC_OPTS[@]}" "$SRC_MNT/" "$DST_MNT/" > "$EXEC_LOG_TEMP" 2>&1
        EXIT_CODE=$?
        cat "$EXEC_LOG_TEMP" >> "$LOG_TEMP"

        if [ "$EXIT_CODE" -eq 0 ]; then
            STATUS="SUCCÈS"
            STATUS_KEY="success"
            LABEL="Succès"
            MESSAGE="Synchronisation terminée."
        else
            STATUS="ÉCHEC"
            STATUS_KEY="failed"
            LABEL="Échec"
            MESSAGE="Rsync a terminé avec une erreur."
        fi
    fi

    finish_job_log "$JOB_ID" "$STATUS_KEY" "$LABEL" "$MODE" "$TRIGGER" "$STARTED_AT" "$START_EPOCH" "$EXIT_CODE" "$MESSAGE" "$LOG_TEMP" "$EXEC_LOG_TEMP"
    rm -f "$EXEC_LOG_TEMP" "$EXCLUDES_FILE"

    [ "$MODE" = "run" ] && send_notification "$NAME" "$STATUS" "$(cat $LOG_TEMP)"

    for MNT in /mnt/rsync_${JOB_ID}_source_* /mnt/rsync_${JOB_ID}_destination_*; do
        [ -d "$MNT" ] || continue
        umount "$MNT" 2>/dev/null || true
        rmdir "$MNT" 2>/dev/null || true
    done
}

mount_test() {
    local JOB_ID="$1"
    local TRIGGER="${2:-manual}"
    local MODE="mount_test"
    local LOG_TEMP="/tmp/rsync_mount_test.log"
    local EXEC_LOG_TEMP
    local JOB
    local NAME
    local SRC_MNT
    local DST_MNT
    local SRC_STATUS
    local DST_STATUS
    local START_EPOCH
    local STARTED_AT
    local EXIT_CODE=0
    local STATUS_KEY="success"
    local LABEL="Montages OK"
    local MESSAGE="Montages vérifiés avec succès."
    local MNT
    local TEST_FILE

    ensure_jobs_file || {
        echo "[TEST] Fichier jobs invalide: $JOBS_FILE" > /proc/1/fd/1
        return 1
    }
    ensure_status_storage

    JOB=$(jq -c --arg id "$JOB_ID" '.[] | select(.id == $id)' "$JOBS_FILE")
    if [ -z "$JOB" ]; then
        echo "[TEST] Job introuvable: id=$JOB_ID" > /proc/1/fd/1
        return 1
    fi

    NAME=$(echo "$JOB" | jq -r '.name')
    START_EPOCH=$(date +%s)
    STARTED_AT=$(date -Iseconds)
    EXEC_LOG_TEMP=$(mktemp)
    : > "$LOG_TEMP"
    {
        echo "--- TEST MONTAGES : $NAME (id $JOB_ID, Déclenchement $TRIGGER) ---"
        echo "Début : $STARTED_AT"
    } | tee -a "$LOG_TEMP" > /proc/1/fd/1

    prepare_test_path() {
        local SIDE_NAME="$1"
        local SIDE="$2"
        local RESULT_VAR="$3"
        local HOST
        local SHARE
        local SUBPATH
        local OLD_PATH
        local USER
        local PASS
        local DOMAIN
        local VERS
        local SEC
        local EXTRA_OPTIONS
        local UNC
        local REST
        local REMOTE
        local MNT
        local CREDS
        local OPTS
        local SAFE_OPTS
        local MOUNT_LOG
        local MOUNT_STATUS

        if [ "$(echo "$SIDE" | jq -r '.type')" = "cifs" ]; then
            HOST=$(echo "$SIDE" | jq -r '.host // ""')
            SHARE=$(echo "$SIDE" | jq -r '.share // ""')
            SUBPATH=$(echo "$SIDE" | jq -r '.subpath // ""')
            OLD_PATH=$(echo "$SIDE" | jq -r '.path // ""')
            USER=$(echo "$SIDE" | jq -r '.user // ""')
            PASS=$(echo "$SIDE" | jq -r '.pass // ""')
            DOMAIN=$(echo "$SIDE" | jq -r '.domain // ""')
            VERS="3.0"
            SEC="ntlmssp"
            EXTRA_OPTIONS="noserverino,nounix"

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
                echo "[CIFS] Configuration $SIDE_NAME incomplète: adresse/partage et login sont obligatoires." | tee -a "$LOG_TEMP" > /proc/1/fd/1
                return 1
            fi

            MNT="/mnt/rsync_${JOB_ID}_${SIDE_NAME}_$(date +%s)"
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
            SAFE_OPTS=$(safe_cifs_options_for_log "$OPTS")
            log_line "[CIFS] Montage test $SIDE_NAME: $REMOTE -> $MNT" "$LOG_TEMP"
            log_line "[CIFS] Options montage test $SIDE_NAME: $SAFE_OPTS${DOMAIN:+, domain=$DOMAIN}" "$LOG_TEMP"
            MOUNT_LOG=$(mktemp)
            mount -v -t cifs "$REMOTE" "$MNT" -o "$OPTS" > "$MOUNT_LOG" 2>&1
            MOUNT_STATUS=$?
            if [ "$MOUNT_STATUS" -ne 0 ]; then
                cat "$MOUNT_LOG" | tee -a "$LOG_TEMP" > /proc/1/fd/1
                echo "[CIFS] Échec montage test $SIDE_NAME." | tee -a "$LOG_TEMP" > /proc/1/fd/1
                rm -f "$CREDS" "$MOUNT_LOG"
                rmdir "$MNT" 2>/dev/null
                return 1
            fi
            rm -f "$CREDS" "$MOUNT_LOG"

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

    prepare_test_path "source" "$(echo "$JOB" | jq -c '.source')" SRC_MNT
    SRC_STATUS=$?
    prepare_test_path "destination" "$(echo "$JOB" | jq -c '.target')" DST_MNT
    DST_STATUS=$?

    if [ "$SRC_STATUS" -ne 0 ] || [ "$DST_STATUS" -ne 0 ]; then
        STATUS_KEY="mount_error"
        LABEL="Erreur montage"
        MESSAGE="Échec montage réseau."
        EXIT_CODE=1
    elif [ ! -d "$SRC_MNT" ] || [ ! -r "$SRC_MNT" ]; then
        STATUS_KEY="mount_error"
        LABEL="Erreur montage"
        MESSAGE="Source inaccessible: $SRC_MNT"
        EXIT_CODE=1
    elif [ ! -d "$DST_MNT" ]; then
        STATUS_KEY="mount_error"
        LABEL="Erreur montage"
        MESSAGE="Destination inaccessible: $DST_MNT"
        EXIT_CODE=1
    else
        TEST_FILE="$DST_MNT/.rsync_manager_write_test_$(date +%s)"
        if ! touch "$TEST_FILE" 2>/dev/null; then
            STATUS_KEY="mount_error"
            LABEL="Erreur montage"
            MESSAGE="Destination non inscriptible: $DST_MNT"
            EXIT_CODE=1
        else
            rm -f "$TEST_FILE"
        fi
    fi

    echo "$MESSAGE" | tee -a "$LOG_TEMP" > "$EXEC_LOG_TEMP"
    finish_job_log "$JOB_ID" "$STATUS_KEY" "$LABEL" "$MODE" "$TRIGGER" "$STARTED_AT" "$START_EPOCH" "$EXIT_CODE" "$MESSAGE" "$LOG_TEMP" "$EXEC_LOG_TEMP"
    rm -f "$EXEC_LOG_TEMP"

    for MNT in /mnt/rsync_${JOB_ID}_source_* /mnt/rsync_${JOB_ID}_destination_*; do
        [ -d "$MNT" ] || continue
        umount "$MNT" 2>/dev/null || true
        rmdir "$MNT" 2>/dev/null || true
    done
}

case "$1" in
    list) ensure_jobs_file && cat "$JOBS_FILE" || echo '[]' ;;
    normalize_jobs) normalize_jobs_file "$2" "${3:-/dev/stdout}" ;;
    save) cat > "$JOBS_FILE"; ensure_jobs_file ;;
    test_email) send_notification "TEST" "OK" "Vérification configuration SMTP." "force" ;;
    mount_test) mount_test "$2" "$3" ;;
    run|dry) run_job "$2" "$1" "$3" ;;
esac
