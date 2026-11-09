#!/bin/bash
# One-time setup from the admin terminal: sign in to claude.ai, then run
# Remote Control once in the foreground so its first-run questions (trust the
# workspace, enable Remote Control) are answered by a person, not the App.
# Claude Code records both answers itself; the background loop reads them.
set -uo pipefail

readonly WORKSPACE="/data/workspace"
readonly CLAUDE_CONFIG="${HOME}/.claude.json"
readonly STATE_DIR="${HOME}/.claude-remote"

setup_done() {
  jq -e --arg ws "${WORKSPACE}" \
    '.remoteDialogSeen == true and .projects[$ws].hasTrustDialogAccepted == true' \
    "${CLAUDE_CONFIG}" >/dev/null 2>&1
}

if ! claude auth status 2>/dev/null | jq -e '.loggedIn == true and .authMethod == "claude.ai"' >/dev/null; then
  echo
  echo "Step 1/2 — Sign in with your Claude subscription (not an API key)."
  echo "Étape 1/2 — Connexion avec ton abonnement Claude (pas une clé API)."
  echo "Open the link on any device; if a code is shown, paste it here."
  echo "Ouvre le lien sur n'importe quel appareil ; si un code s'affiche, colle-le ici."
  echo
  claude auth login || exit 1
fi
claude auth status --text || true

if setup_done; then
  echo
  echo "Remote Control is already set up: the App runs it in the background."
  echo "Remote Control est déjà installé : l'App le fait tourner en arrière-plan."
  echo "Phone / téléphone : Claude app → Code → \"Home Assistant\"."
  exit 0
fi

# The background loop waits while this lock is held, so only one Remote
# Control runs at a time. It is released when this script ends, including
# when the terminal is closed.
mkdir -p "${STATE_DIR}"
exec {setup_lock}>"${STATE_DIR}/setup.lock"
if ! flock -n "${setup_lock}"; then
  echo "claude-remote-setup is already running in another terminal. / claude-remote-setup tourne déjà dans un autre terminal."
  exit 1
fi

cat <<EOF

Step 2/2 — Remote Control now runs here once. Answer its two questions:
trust ${WORKSPACE}, then "Enable Remote Control? (y/n)" → y.
When it shows it is ready, press Ctrl-C or close the terminal: the App then
starts it in the background within 20 seconds.

Étape 2/2 — Remote Control tourne ici une fois. Réponds à ses deux questions :
faire confiance à ${WORKSPACE}, puis « Enable Remote Control? (y/n) » → y.
Quand il indique qu'il est prêt, fais Ctrl-C ou ferme le terminal : l'App le
démarre ensuite en arrière-plan d'ici 20 secondes.

EOF

# Keep this script alive on Ctrl-C while Claude receives the signal normally.
# Claude does not inherit the lock, so a leftover child cannot keep it held.
trap ':' INT
cd "${WORKSPACE}"
claude remote-control --name "Home Assistant" --permission-mode default {setup_lock}>&-
trap - INT
exec {setup_lock}>&-

echo
if setup_done; then
  echo "Done. Remote Control starts in the background within 20 seconds."
  echo "Terminé. Remote Control démarre en arrière-plan d'ici 20 secondes."
  echo "Phone / téléphone : Claude app → Code → \"Home Assistant\"."
else
  echo "Setup not complete: both questions must be accepted. Run claude-remote-setup again."
  echo "Installation incomplète : il faut accepter les deux questions. Relance claude-remote-setup."
fi
