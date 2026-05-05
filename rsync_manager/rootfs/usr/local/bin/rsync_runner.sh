#!/bin/bash
set -e

QUEUE_DIR="/tmp/rsync_manager_queue"
mkdir -p "$QUEUE_DIR"

echo "[RUNNER] Démarrage du runner de jobs." > /proc/1/fd/1

while true; do
    for JOB_FILE in "$QUEUE_DIR"/*.job; do
        [ -e "$JOB_FILE" ] || continue

        PROCESSING_FILE="${JOB_FILE}.running"
        if ! mv "$JOB_FILE" "$PROCESSING_FILE" 2>/dev/null; then
            continue
        fi

        read -r ACTION INDEX < "$PROCESSING_FILE" || true
        rm -f "$PROCESSING_FILE"

        case "$ACTION" in
            run|dry) ;;
            *)
                echo "[RUNNER] Action ignorée: $ACTION" > /proc/1/fd/1
                continue
                ;;
        esac

        if ! printf '%s' "$INDEX" | grep -Eq '^[0-9]+$'; then
            echo "[RUNNER] Index ignoré: $INDEX" > /proc/1/fd/1
            continue
        fi

        echo "[RUNNER] Exécution demandée: $ACTION job $INDEX" > /proc/1/fd/1
        /usr/local/bin/rsync_manager.sh "$ACTION" "$INDEX" > /proc/1/fd/1 2>&1 || true
    done

    sleep 1
done
