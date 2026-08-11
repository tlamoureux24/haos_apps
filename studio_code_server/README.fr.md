# Studio Code Server + Codex

App Home Assistant expérimentale fournissant un espace de développement
persistant accessible exclusivement par l’Ingress Home Assistant.

Elle vise à retrouver à distance un environnement proche de VS Code avec Git,
SSH, les outils Home Assistant et Codex, notamment depuis un ordinateur ou un
smartphone connecté au VPN du réseau domestique.

## État expérimental

Cette version `0.1.x` sert à valider la compatibilité réelle de code-server avec
Home Assistant OS et Codex. Ne pas l’utiliser comme unique copie d’un dépôt ou
d’une clé SSH importante.

Codex CLI est le mode d’utilisation de référence. L’extension IDE officielle
Codex est incluse pour évaluation, mais OpenAI ne documente pas officiellement
code-server parmi ses éditeurs compatibles. Elle peut donc ne pas se charger ou
perdre certaines fonctions.

## Fonctionnalités

- code-server 4.132.0 accessible uniquement par l’Ingress authentifié ;
- terminal `zsh` et `bash` ;
- Git, client OpenSSH, Home Assistant CLI, Python, Node.js, rsync et outils usuels ;
- Codex CLI 0.147.0, sans clé OpenAI Platform imposée ;
- connexion à l’abonnement ChatGPT par OAuth Device Code ;
- extensions Codex, Home Assistant Config Helper et YAML préinstallées ;
- persistance des réglages VS Code, extensions, dépôts, clés SSH, configuration Git, historique et données Codex ;
- accès en écriture à la configuration Home Assistant et aux configurations des Apps.

## Premier démarrage

1. Installer et démarrer l’App.
2. Activer **Afficher dans la barre latérale**.
3. Ouvrir **Code + Codex** depuis Home Assistant.
4. Dans le menu `Terminal`, créer un terminal.
5. Exécuter :

```bash
codex login --device-auth
```

6. Ouvrir l’adresse indiquée, se connecter au compte ChatGPT et saisir le code temporaire.
7. Vérifier ensuite :

```bash
codex --version
codex
```

Les jetons OAuth sont conservés dans le stockage privé de l’App. Ils ne doivent
jamais être copiés dans un dépôt Git, un ticket ou une conversation.

## Git et SSH

Configurer l’identité Git une seule fois :

```bash
git config --global user.name "Votre nom"
git config --global user.email "votre-adresse@example.com"
```

Les fichiers suivants persistent après redémarrage et mise à jour :

- `/data/home/.gitconfig` ;
- `/data/home/.ssh` ;
- `/data/home/.codex` ;
- `/data/workspace` ;
- `/data/vscode`.

Le dossier `/data/workspace` est privé à l’App et inclus dans ses sauvegardes à
froid. Il convient aux clones Git utilisés depuis cet environnement.

## Permissions

Cette App est une console d’administration et non un simple éditeur :

- rôle Supervisor `manager` ;
- API Home Assistant ;
- écriture dans `/config`, `/addon_configs`, `/addons` et `/share` ;
- terminal root dans le conteneur ;
- accès sortant à Internet.

L’App n’expose aucun port direct. code-server désactive son authentification
interne parce que l’authentification et le routage sont assurés par l’Ingress
Home Assistant. Ne jamais ajouter un port public au conteneur sans ajouter une
authentification indépendante.

## Options

- `log_level` : niveau de détail du journal ;
- `workspace_path` : dossier ouvert au démarrage, `/data/workspace` par défaut ;
- `packages` : paquets Debian supplémentaires installés à chaque démarrage ;
- `init_commands` : commandes root exécutées à chaque démarrage.

Les deux dernières options donnent volontairement beaucoup de pouvoir. Ne pas
y placer de commande provenant d’une source non vérifiée.

## Limites du test initial

- ergonomie smartphone à évaluer réellement ;
- extension Codex non garantie dans code-server ;
- image disponible uniquement pour `amd64` et `aarch64` ;
- consommation mémoire potentiellement importante ;
- mises à jour automatiques internes désactivées : toute mise à jour passe par une nouvelle version de l’App.

## Origine

Cette App reprend les bases du projet MIT
[hassio-addons/addon-vscode](https://github.com/hassio-addons/addon-vscode).
Les attributions et la politique de reprise figurent dans `LICENSE.upstream.md`,
`THIRD_PARTY.md` et `UPSTREAM.md`.
