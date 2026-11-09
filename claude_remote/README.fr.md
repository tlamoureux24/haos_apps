# Claude Remote

Documentation : [Français](README.fr.md) | [English](README.md)

Claude Remote fait tourner [Claude Code](https://code.claude.com/docs) en mode **Remote Control** dans Home Assistant. On l'utilise depuis l'app Claude sur le téléphone ou depuis claude.ai/code, sans PC allumé et sans exposer quoi que ce soit sur Internet.

Claude n'a **aucun accès direct** à Home Assistant : il passe uniquement par le serveur MCP de l'App [HA-MCP](https://github.com/homeassistant-ai/ha-mcp). La lecture seule ou la lecture/écriture se règle dans HA-MCP, pas ici.

## Fonctionnement

```text
Téléphone / navigateur ──HTTPS──▶ Anthropic ◀──HTTPS sortant── Claude Remote ──▶ HA-MCP ──▶ Home Assistant
```

- L'App ouvre seulement une connexion **sortante** vers Anthropic. Aucun port entrant, aucun reverse proxy.
- L'interface dans la barre latérale (Ingress) sert à l'installation, à l'état et au journal d'activité. Elle est réservée aux administrateurs HA.
- `boot: manual` : l'App ne démarre que lorsque tu la lances.

## Prérequis

- Un abonnement Claude (Pro, Max, Team ou Enterprise). Remote Control ne fonctionne pas avec une clé API.
- L'App HA-MCP installée et démarrée.

## Installation

1. Installer l'App depuis ce dépôt.
2. Dans l'App HA-MCP, copier l'URL privée, de la forme `http://192.168.1.15:9583/private_xxxx`.
3. Dans la configuration de Claude Remote, coller cette URL dans **URL privée HA-MCP**, puis démarrer l'App.
4. Ouvrir l'App, puis **Ouvrir le terminal**, et lancer :

   ```bash
   claude-remote-setup
   ```

   - Étape 1 : connexion à ton compte Claude. Ouvre le lien affiché sur n'importe quel appareil ; si un code apparaît, colle-le dans le terminal.
   - Étape 2 : Remote Control démarre une fois au premier plan. Accepte ses questions (faire confiance à `/data/workspace`, activer Remote Control). Quand il indique qu'il est prêt, fais Ctrl-C ou ferme le terminal.
5. Moins de 20 secondes plus tard, Remote Control tourne en arrière-plan. Sur le téléphone : app Claude → **Code** → environnement **Home Assistant**.

## Options

| Option | Description |
| --- | --- |
| `ha_mcp_url` | URL privée affichée par l'App HA-MCP, terminant par `/private_<secret>`. Vide : Claude n'a accès à rien. Elle n'est jamais écrite dans les logs ni dans le journal. |
| `confirm_writes` | Activé par défaut : les outils de lecture HA-MCP (`ha_get_*`, `ha_list_*`, `ha_search*`, `ha_config_get_*`, `ha_config_list_*`, `ha_eval_template`) s'exécutent directement, et tout autre outil demande ta validation dans l'app Claude. Désactivé : tous les outils HA-MCP s'exécutent sans demande. |
| `log_level` | Niveau de détail du journal de l'App. |

## Modèle de sécurité

Du plus fort au plus faible :

1. **HA-MCP est la vraie barrière.** Coche `read_only_mode` dans l'App HA-MCP pour une lecture seule stricte, ou utilise `disabled_tools` outil par outil. Attention : ce réglage s'applique à tous les clients de HA-MCP, ton PC compris.
2. **Aucun privilège Home Assistant dans l'App.**
   - Aucun dossier monté (`/config`, `/share`, configs des Apps…).
   - `hassio_api: false` et `homeassistant_api: false`.
   - Pas de port publié ; l'Ingress n'accepte que le proxy de HA.
   - Claude Code et le terminal tournent sous un utilisateur non privilégié (uid 1000), avec un environnement vidé : pas de token Supervisor.
3. **Règles Claude Code figées dans l'image** (`/etc/claude-code`, non modifiables par l'utilisateur ni par un projet).
   - Seul le serveur MCP `home-assistant` existe. Aucun autre ne peut être ajouté, ni depuis le terminal, ni depuis le téléphone, ni par les connecteurs claude.ai.
   - Les outils internes sont interdits : shell (`Bash`), lecture et écriture de fichiers, `WebFetch`, `WebSearch`, sous-agents, etc. Claude ne peut donc ni appeler l'URL du MCP lui-même, ni lire le fichier qui la contient.
   - Les modes qui sautent les validations (`bypassPermissions`, `auto`) sont désactivés, et seuls les hooks et règles de l'App s'appliquent.
   - Mises à jour automatiques, télémétrie et rapports d'erreur désactivés. Claude Code est mis à jour par une nouvelle version de l'App, figée par version et par empreinte SHA-512.
4. **Profil AppArmor, appliqué par le noyau.** Claude Code tourne dans son propre sous-profil : il ne peut écrire que dans son dossier personnel, l'espace de travail et `/tmp`, et ne peut lancer aucun script de l'App. Tout programme qu'il lance (shell, ripgrep…) bascule dans un second sous-profil sans réseau, sans accès à la connexion Claude ni à l'URL HA-MCP, et sans pouvoir relancer Claude. Même si les règles ci-dessus étaient contournées, un shell lancé par Claude ne pourrait rien envoyer à l'extérieur.
5. **Cycle de vie.** Démarre et arrête l'App, et si tu veux l'App HA-MCP, quand tu en as besoin : depuis l'app compagnon HA, ou avec un bouton de tableau de bord qui appelle `hassio.app_start` / `hassio.app_stop`.

Ce qui reste possible : le conteneur garde un accès Internet sortant, nécessaire pour joindre Anthropic. Sans shell ni `WebFetch`, Claude n'a pas de moyen direct d'envoyer des données ailleurs, et AppArmor coupe le réseau de tout programme qu'il lance.

Le terminal d'administration donne un shell sous l'utilisateur non privilégié de l'App. Il est réservé aux administrateurs HA et n'a ni token Home Assistant ni accès à la configuration.

## Données et sauvegardes

- `/data/home` : compte Claude, réglages et historique des sessions.
- Les identifiants (`.credentials.json`) et l'historique des conversations sont **exclus des sauvegardes** HA. Après une restauration, relance `claude-remote-setup`.
- La connexion claude.ai finit par expirer ; Claude Code prévient 3 jours avant. Remote Control s'arrête alors, et l'App repasse en « en attente de connexion » : relance `claude auth login` dans le terminal.
- Le journal d'activité (`/data/activity.jsonl`) ne contient que des événements techniques, gardés 30 jours ou 10 000 entrées au plus. Il ne contient jamais de prompt, de résultat d'outil, d'URL ni d'identifiant.

## Dépannage

| Symptôme | Piste |
| --- | --- |
| « en attente de connexion » | Lancer `claude-remote-setup` ou `claude auth login` dans le terminal. |
| « en attente d'installation » | Relancer `claude-remote-setup` et accepter les deux questions (faire confiance à `/data/workspace`, puis `y`). |
| HA-MCP injoignable | Vérifier que l'App HA-MCP est démarrée et que l'URL est correcte. Si l'IP de HA change, essayer `http://172.30.32.1:9583/private_xxxx`. |
| Remote Control redémarre en boucle | Lire le journal de l'App. |
