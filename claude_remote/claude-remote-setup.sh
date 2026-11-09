#!/bin/bash
# One-time setup from the admin terminal: sign in to claude.ai, then run
# Remote Control once in the foreground so its first-run questions (trust the
# workspace, enable Remote Control) are answered by a person, not the App.
set -uo pipefail

readonly MARKER="${HOME}/.claude-remote/setup-done"
readonly WORKSPACE="/data/workspace"

if [[ -f "${MARKER}" ]]; then
  echo "Remote Control is already set up. / Remote Control est déjà installé."
  echo "To redo it / Pour recommencer : rm ${MARKER}, restart the App / redémarrer l'App, then / puis claude-remote-setup."
  exit 0
fi

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

cat <<EOF

Step 2/2 — Remote Control now runs here once. Accept its questions
(trust ${WORKSPACE}, enable Remote Control). When it shows it is ready,
press Ctrl-C: the App then keeps it running in the background.

Étape 2/2 — Remote Control tourne ici une fois. Accepte ses questions
(faire confiance à ${WORKSPACE}, activer Remote Control). Quand il indique
qu'il est prêt, fais Ctrl-C : l'App le fait ensuite tourner en arrière-plan.

EOF

# Keep this script alive on Ctrl-C while Claude receives the signal normally.
trap ':' INT
cd "${WORKSPACE}"
claude remote-control --name "Home Assistant" --permission-mode default
trap - INT

echo
read -r -p "Did Remote Control show it was ready? / Remote Control était-il prêt ? [y/N] " answer
if [[ "${answer}" =~ ^[yYoO] ]]; then
  mkdir -p "$(dirname "${MARKER}")"
  touch "${MARKER}"
  echo "Done. Remote Control starts in the background within 20 seconds."
  echo "Terminé. Remote Control démarre en arrière-plan d'ici 20 secondes."
  echo "Phone / téléphone : Claude app → Code → \"Home Assistant\"."
else
  echo "Setup not saved; run claude-remote-setup again. / Installation non enregistrée ; relance claude-remote-setup."
fi
