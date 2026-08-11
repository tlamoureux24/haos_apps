# OpenClaw pour Home Assistant

[English documentation](README.md)

Cette App Home Assistant exécute l'image officielle OpenClaw sur Home Assistant
OS ou une installation supervisée. Elle ajoute uniquement l'intégration HAOS
et la préparation du stockage persistant.

## Principes

- image officielle `ghcr.io/openclaw/openclaw` épinglée par version ;
- exécution amont sous l'utilisateur non privilégié `node` ;
- aucun navigateur, Homebrew, socket Docker ou réseau hôte ;
- CLI OpenClaw non privilégiée via l’Ingress HA réservé aux administrateurs ;
- aucune clé OpenAI Platform et aucun repli vers une API facturée ;
- authentification de l'abonnement ChatGPT/Codex par OAuth OpenAI ;
- connexion OAuth par code depuis la CLI Ingress réservée aux administrateurs ;
- accès local/VPN HTTPS/WSS au Gateway sur le port 18789, protégé par jeton,
  certificat persistant et appairage ;
- connexion facultative directe au serveur Streamable HTTP de HA-MCP existant ;
- URL d’appairage mobile explicite pour générer un QR utilisable hors du réseau Docker ;
- sauvegardes HA à froid et profil AppArmor personnalisé ;
- mises à jour amont stables automatisées avec validation et test de démarrage.

Consultez [DOCS.md](DOCS.md) avant le premier démarrage, notamment pour
l'origine navigateur, l'URL d'appairage mobile et l'authentification OAuth par CLI.

## Configuration OAuth

Ouvrez **OpenClaw CLI** via l’Ingress Home Assistant réservé aux administrateurs,
puis exécutez :

```bash
openclaw models auth login --provider openai --device-code
```

Suivez la procédure avec le code temporaire et le compte ChatGPT qui porte
l’abonnement, puis redémarrez l’App une fois. Les profils OAuth existants restent
dans le stockage privé persistant de l’App lors des mises à jour d’image.

## Projet amont

- OpenClaw : https://github.com/openclaw/openclaw
- Documentation Docker : https://docs.openclaw.ai/install/docker
- Licence : MIT
