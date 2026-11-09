#!/bin/bash
# Admin terminal opened through Home Assistant Ingress (ttyd).
# Runs as the unprivileged claude user, without Supervisor credentials.
set -euo pipefail

cd /data/workspace

cat <<'EOF'

  Claude Remote — admin terminal / terminal d'administration

  First setup / Première installation :  claude-remote-setup
  Check / Vérifier :                     claude auth status --text
  Sign out / Déconnexion :               claude auth logout

  After setup, Remote Control runs in the background: use the Claude app,
  Code tab, "Home Assistant" environment.
  Après l'installation, Remote Control tourne en arrière-plan : app Claude,
  onglet Code, environnement « Home Assistant ».

  Claude only reaches Home Assistant through the HA-MCP server; read-only
  or read/write access is chosen in the HA-MCP App.
  Claude n'accède à Home Assistant que via le serveur HA-MCP ; la lecture
  seule ou la lecture/écriture se choisit dans l'App HA-MCP.

EOF

exec /bin/bash --login
