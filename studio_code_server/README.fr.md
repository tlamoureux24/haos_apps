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
Codex peut être installée séparément pour évaluation, mais OpenAI ne documente pas officiellement
code-server parmi ses éditeurs compatibles. Elle peut donc ne pas se charger ou
perdre certaines fonctions.

## Fonctionnalités

- code-server 4.132.0 accessible uniquement par l’Ingress authentifié ;
- terminal `zsh` et `bash` ;
- Git, client OpenSSH, Home Assistant CLI, Python, Node.js, rsync et outils usuels ;
- Codex CLI 0.147.0, sans clé OpenAI Platform imposée ;
- connexion à l’abonnement ChatGPT par OAuth Device Code ;
- extensions Home Assistant Config Helper et YAML préinstallées ;
- installateur manuel facultatif de l’extension Codex expérimentale ;
- persistance des réglages VS Code, extensions, dépôts, clés SSH, configuration Git, historique et données Codex ;
- récupération automatique des informations Git distantes, sans fusion ni `pull` automatique ;
- configuration facultative de HA-MCP directement depuis les options protégées de l’App ;
- accès en écriture à la configuration Home Assistant et aux configurations des Apps.
- exécution de Codex et de ses commandes sous un utilisateur dédié non privilégié, sans jeton Supervisor dans son environnement.

## Premier démarrage

1. Installer et démarrer l’App.
2. Activer **Afficher dans la barre latérale**.
3. Ouvrir **Code + Codex** depuis Home Assistant.
4. Dans le menu `Terminal`, créer un terminal. L’éditeur et tous ses terminaux
   utilisent l’utilisateur non privilégié `codex`.
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

## Essai facultatif de l’extension Codex

Le CLI doit d’abord être validé. Pour tester ensuite l’interface Codex intégrée
à l’éditeur, exécuter volontairement :

```bash
install-codex-extension
```

Le téléchargement compressé représente environ 200 Mo et l’extension occupe
environ 550 Mo. Elle est installée dans le stockage persistant, sans alourdir la
construction de l’App ni son démarrage. Recharger ensuite la fenêtre du
navigateur. Son fonctionnement sous code-server n’est pas garanti.

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

code-server exécute automatiquement `git fetch` à intervalles réguliers. Il
signale ainsi les nouveaux commits distants, mais ne modifie jamais la branche
locale : le `pull` reste une action volontaire.

## Home Assistant via HA-MCP

Copier l’URL privée Streamable HTTP affichée par l’App HA-MCP dans l’option
protégée **URL privée HA-MCP**, puis redémarrer cette App. Elle configure alors
automatiquement un serveur Codex nommé `home-assistant`. L’URL doit se terminer
par `/private_<secret>` et ne doit jamais être placée dans Git ou une capture.

Après redémarrage, recharger la fenêtre de l’éditeur et demander à Codex de
vérifier la disponibilité du serveur sans exécuter d’outil. Les permissions
effectives sont celles exposées par HA-MCP ; commencer en lecture seule est
recommandé.

## Permissions

Cette App possède des accès administratifs au niveau du conteneur de démarrage :

- rôle Supervisor `manager` ;
- API Home Assistant ;
- écriture dans `/config`, `/addon_configs`, `/addons` et `/share` ;
- accès sortant à Internet.

code-server, son hôte d’extensions, tous les terminaux et Codex utilisent le
compte `codex` (UID 1000), sans les variables `SUPERVISOR_TOKEN` et
`HASS_TOKEN`. Le workspace et les données OAuth/Git/SSH lui appartiennent. Les
paquets supplémentaires et `init_commands` sont traités comme root uniquement
pendant le démarrage, avant le lancement de l’interface interactive.

HAOS peut toujours refuser l’isolation Linux `bubblewrap`. Dans ce cas, Codex
continue à demander les approbations prévues, mais celles-ci ne remplacent pas
un véritable bac à sable système. Ne pas approuver une commande dont la portée
n’est pas comprise. Donner des privilèges Docker supplémentaires pour forcer
`bubblewrap` est volontairement exclu.

L’App n’expose aucun port direct. code-server désactive son authentification
interne parce que l’authentification et le routage sont assurés par l’Ingress
Home Assistant. Ne jamais ajouter un port public au conteneur sans ajouter une
authentification indépendante.

## Options

- `log_level` : niveau de détail du journal ;
- `workspace_path` : dossier ouvert au démarrage, `/data/workspace` par défaut ;
- `ha_mcp_url` : URL privée HA-MCP facultative, enregistrée comme valeur protégée ;
- `packages` : paquets Debian supplémentaires installés à chaque démarrage ;
- `init_commands` : commandes root exécutées à chaque démarrage.

Les deux dernières options donnent volontairement beaucoup de pouvoir. Ne pas
y placer de commande provenant d’une source non vérifiée.

## Limites du test initial

- ergonomie smartphone à évaluer réellement ;
- extension Codex facultative et non garantie dans code-server ;
- image disponible uniquement pour `amd64` et `aarch64` ;
- consommation mémoire potentiellement importante ;
- mises à jour automatiques internes désactivées : toute mise à jour passe par une nouvelle version de l’App.

## Origine

Cette App reprend les bases du projet MIT
[hassio-addons/addon-vscode](https://github.com/hassio-addons/addon-vscode).
Les attributions et la politique de reprise figurent dans `LICENSE.upstream.md`,
`THIRD_PARTY.md` et `UPSTREAM.md`.
