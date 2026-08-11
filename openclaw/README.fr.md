# OpenClaw pour Home Assistant

[English documentation](README.md)

Cette App Home Assistant exécute l'image officielle OpenClaw sur Home Assistant
OS ou une installation supervisée. Elle ajoute uniquement l'intégration HAOS
et la préparation du stockage persistant.

## Principes

- image officielle `ghcr.io/openclaw/openclaw` épinglée par version ;
- exécution amont sous l'utilisateur non privilégié `node` ;
- aucun navigateur, terminal Web, Homebrew, socket Docker ou réseau hôte ;
- aucune clé OpenAI Platform et aucun repli vers une API facturée ;
- authentification de l'abonnement ChatGPT/Codex par OAuth OpenAI ;
- accès local/VPN au Gateway sur le port 18789, protégé par jeton et appairage
  par défaut, avec un mode de test HTTP temporaire explicite ;
- connexion facultative directe au serveur Streamable HTTP de HA-MCP existant ;
- sauvegardes HA à froid et profil AppArmor personnalisé ;
- mises à jour amont stables automatisées avec validation et test de démarrage.

Consultez [DOCS.md](DOCS.md) avant le premier démarrage, notamment pour
l'origine navigateur et l'authentification OAuth.

## Projet amont

- OpenClaw : https://github.com/openclaw/openclaw
- Documentation Docker : https://docs.openclaw.ai/install/docker
- Licence : MIT
