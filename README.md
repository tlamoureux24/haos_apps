# Thibs's Home Assistant Apps

[Français](#français) | [English](#english)

## Français

Dépôt d’Apps pour Home Assistant OS et les installations avec Supervisor. Chaque App dispose d’une documentation détaillée en français et en anglais.

### Installation du dépôt

#### Installation avec My Home Assistant

[![Ouvrir Home Assistant et afficher la boîte de dialogue d’ajout d’un dépôt d’Apps avec ce dépôt prérempli.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Ftlamoureux24%2Fhaos_apps)

#### Installation manuelle

1. Ouvrir Home Assistant.
2. Aller dans `Paramètres` > `Modules complémentaires` > `Boutique des modules complémentaires`.
3. Ouvrir le menu en haut à droite, puis sélectionner `Dépôts`.
4. Ajouter l’URL du dépôt :

```text
https://github.com/tlamoureux24/haos_apps
```

5. Cliquer sur `Ajouter`, puis recharger la boutique si nécessaire.
6. Installer l’App souhaitée depuis la boutique.

### Apps disponibles

#### MCP Capability Bridge

Socle expérimental d’une App MCP autonome transformant des accès techniques
non-MCP en capacités strictement bornées. La version 0.1.0 fournit uniquement
le shell HAOS, les surfaces réseau isolées et l’interface Ingress commune à la
suite ; aucun endpoint MCP ni adaptateur n’est encore activé.

Documentation détaillée :

- [Documentation française](mcp_capability_bridge/README.fr.md)

#### Agent Control Plane

Plan de contrôle stable entre des agents authentifiés et un ou plusieurs
serveurs MCP configurables. Elle agit comme un pare-feu applicatif MCP
deny-by-default : la configuration explicite de l’administrateur constitue
l’autorisation, et seuls les outils et arguments compris dans l’enveloppe exacte
de la tâche sont exposés à l’agent.

Fonctionnalités principales :

- connecteurs MCP Streamable HTTP génériques et inventaires indépendants ;
- tâches composées d’outils précis provenant d’un ou plusieurs connecteurs ;
- restrictions facultatives d’arguments fixes par outil, avec valeurs sensibles
  chiffrées et retirées du schéma exposé à l’agent ;
- outils virtuels uniques, même si plusieurs serveurs publient le même nom ;
- autorisation deny-by-default fondée sur la sélection explicite des capacités,
  sans classe spéciale imposée selon qu’un outil lit ou modifie l’état amont ;
- exécutions manuelles, planifiées ou déclenchées par événements authentifiés ;
- file persistante, rapports structurés, rétention et audit chaîné ;
- archivage réversible des tâches et connecteurs sans perte d’historique ;
- interface Ingress bilingue français/anglais avec métriques opérationnelles ;
- secrets des connecteurs conservés dans la passerelle, modifiables uniquement
  par une rotation explicite et jamais transmis aux agents.

Documentation détaillée :

- [Documentation française](agent_control_plane/README.fr.md)

#### Studio Code Server + Codex

App Home Assistant expérimentale fournissant un espace de développement persistant accessible exclusivement par l’Ingress authentifié de Home Assistant.

Fonctionnalités principales :

- code-server récent avec terminal intégré ;
- Git, SSH, Home Assistant CLI, Python et Node.js ;
- Codex CLI avec connexion OAuth à l’abonnement ChatGPT, sans clé OpenAI Platform imposée ;
- éditeur, extensions et terminaux exécutés sous un compte non privilégié ;
- extension officielle Codex installable facultativement depuis le Marketplace de l’éditeur ;
- persistance des dépôts, clés SSH, réglages Git, sessions Codex, paramètres et extensions ;
- récupération Git automatique et connexion HA-MCP facultative configurée depuis l’App ;
- exécution de Codex sous un compte non privilégié sans jeton Supervisor hérité ;
- accès administratif à la configuration Home Assistant et aux configurations des Apps ;
- aucun port direct : accès uniquement par Home Assistant et le VPN utilisé pour joindre Home Assistant.

Documentation détaillée :

- [Documentation française](studio_code_server/README.fr.md)

#### Rsync Manager

App Home Assistant avec interface Ingress pour configurer, planifier, tester et lancer des synchronisations `rsync`.

Fonctionnalités principales :

- tâches `rsync` planifiées par cron ;
- sources et destinations locales ou SMB/CIFS ;
- simulation, exécution manuelle et test des montages ;
- exclusions `rsync` et activation ou désactivation des tâches ;
- dernier statut et dernier journal par tâche ;
- rapports par e-mail via SMTP ;
- import et export des paramètres e-mail et des tâches.

Documentation détaillée :

- [Documentation française](rsync_manager/README.fr.md)

#### UniFi Autoblock

App Home Assistant locale qui reçoit les webhooks UniFi Alarm Manager `Threat Detected and Blocked`, valide les événements IDS/IPS et ajoute l’adresse IPv4 publique de l’attaquant à une liste UniFi `IPV4_ADDRESSES` existante.

L’App ne crée pas elle-même de règle de pare-feu. Elle met à jour la liste d’adresses IP utilisée par une règle UniFi existante, par exemple une liste `IP BAN` appliquée à un reverse proxy ou à un service exposé.

Fonctionnalités principales :

- endpoint webhook local pour UniFi Alarm Manager ;
- authentification par jeton d’URL et jeton Bearer générés automatiquement ;
- validation stricte des événements UniFi IDS/IPS entrants ;
- ajout d’adresses IPv4 publiques uniquement, avec exclusion des adresses locales, privées, réservées et IPv6 ;
- détection automatique du site UniFi et de la liste IPv4 lorsque la configuration le permet ;
- sauvegarde JSON de la liste avant chaque écriture ;
- durée de conservation configurable pour les adresses gérées par l’App ;
- clé API UniFi chiffrée dans `/data`, puis retirée de la configuration ;
- événement Home Assistant `unifi_autoblock_ip_banned` après un bannissement confirmé.

Documentation détaillée :

- [Documentation française](unifi_autoblock/README.fr.md)

#### UniFi Log Explorer

App Home Assistant autonome pour collecter, conserver et explorer localement
les Traffic Flows et événements CEF/Syslog d’un environnement UniFi.

Fonctionnalités principales :

- collecte des Traffic Flows par l’API locale UniFi avec déduplication et
  réconciliation des publications tardives ;
- réception Syslog/CEF en UDP avec filtrage strict des adresses sources ;
- vue d’ensemble sur 24 heures et classements interactifs ;
- explorateurs Traffic Flows et CEF/Syslog avec recherche, filtres et pagination ;
- interface web autonome avec compte administrateur, thèmes clair et sombre ;
- clé API chiffrée localement puis retirée des options Home Assistant ;
- rétention configurable, sauvegarde à froid et export diagnostic sans secret ;
- page Paramètres avec test API et configuration Home Assistant en lecture seule.

Documentation détaillée :

- [Documentation française](unifi_log_explorer/README.fr.md)

#### Nginx Proxy Manager

Enveloppe Home Assistant minimale autour de l’image Docker officielle Nginx Proxy Manager. L’App conserve toutes les fonctionnalités de NPM sans fork ni modification et ajoute uniquement l’intégration nécessaire au Supervisor.

Fonctionnalités principales :

- image officielle Nginx Proxy Manager épinglée sur une version stable ;
- version de l’App alignée sur NPM au format `<version NPM>-<révision>` ;
- ports standards 80, 81 et 443, sans Ingress Home Assistant ;
- données NPM persistées dans `/data` ;
- certificats et configuration Let’s Encrypt persistés dans `/data/letsencrypt` ;
- sauvegarde Home Assistant à froid pour garantir la cohérence de SQLite ;
- détection, validation et préparation automatisées des nouvelles versions NPM ;
- installation volontaire des mises à jour depuis Home Assistant.

Documentation détaillée :

- [Documentation française](nginx_proxy_manager/README.fr.md)

#### Gatus

App Home Assistant basée sur le binaire officiel Gatus pour surveiller les équipements et services du réseau.

Fonctionnalités principales :

- version officielle Gatus épinglée et mise à jour automatiquement dans le dépôt ;
- contrôles ICMP exécutés sans root et sans capacité `NET_RAW` ;
- configuration éditable dans le dossier `addon_config` dédié ;
- identifiants SMS Free Mobile, paramètres SMTP et jeton Home Assistant facultatif injectés depuis les options privées ;
- publication facultative des alertes Gatus dans Home Assistant via les événements `gatus_alert` ;
- aucun secret dans le fichier Gatus ou dans le dépôt GitHub ;
- interface locale sur le port 8080, sans Ingress ;
- profil AppArmor, watchdog interne et sauvegarde à froid ;
- configuration initiale limitée à un contrôle loopback local, sans adresse externe.

Documentation détaillée :

- [Documentation française](gatus/README.fr.md)

#### AdGuard Home

App Home Assistant minimale basée sur l’image Docker officielle AdGuard Home pour filtrer les publicités, traqueurs et domaines indésirables au niveau DNS.

Fonctionnalités principales :

- image officielle AdGuard Home épinglée sur une version stable ;
- version de l’App alignée au format `<version AdGuard Home>-<révision>` ;
- DNS TCP/UDP et interface d’administration activés par défaut ;
- ports DoH, DoH3, DoT, DoQ, DNSCrypt et diagnostic disponibles séparément ;
- réseau bridge sans `host_network`, Ingress ni API Supervisor ;
- authentification administrateur AdGuard Home indépendante de Home Assistant ;
- exécution non-root avec AppArmor et privilèges minimaux ;
- configuration, statistiques et journaux persistés dans `addon_config` ;
- sauvegarde à froid et suivi automatisé des nouvelles versions officielles ;
- DHCP volontairement absent, car il nécessite les broadcasts de niveau 2 et le réseau hôte.

Documentation détaillée :

- [Documentation française](adguard_home/README.fr.md)

### Prérequis

Ce dépôt est destiné aux installations Home Assistant avec Supervisor, notamment :

- Home Assistant OS ;
- Home Assistant Supervised.

Il n’est pas destiné à une installation Home Assistant Core seule sans Supervisor, car les Apps Home Assistant dépendent du Supervisor.

### Convention du dépôt

- [Convention commune d’internationalisation](INTERNATIONALIZATION.md#français)

### Mises à jour

Home Assistant surveille les dépôts d’Apps ajoutés à la boutique. Lorsqu’une nouvelle version d’une App est publiée, elle apparaît comme mise à jour disponible dans l’interface Home Assistant.

Si la nouvelle version n’apparaît pas :

1. Aller dans `Paramètres` > `Modules complémentaires` > `Boutique des modules complémentaires`.
2. Ouvrir le menu en haut à droite.
3. Sélectionner `Rechercher les mises à jour` ou recharger la boutique.

### Support

Pour comprendre le fonctionnement d’une App ou obtenir de l’aide, consulter d’abord sa documentation française :

- [Agent Control Plane](agent_control_plane/README.fr.md)
- [Rsync Manager](rsync_manager/README.fr.md)
- [Studio Code Server + Codex](studio_code_server/README.fr.md)
- [UniFi Autoblock](unifi_autoblock/README.fr.md)
- [UniFi Log Explorer](unifi_log_explorer/README.fr.md) — exploration locale des Traffic Flows et événements CEF/Syslog
- [Nginx Proxy Manager](nginx_proxy_manager/README.fr.md)
- [Gatus](gatus/README.fr.md)
- [AdGuard Home](adguard_home/README.fr.md)

---

## English

App repository for Home Assistant OS and installations with Supervisor. Each App provides detailed documentation in both French and English.

### Repository installation

#### Installation with My Home Assistant

[![Open Home Assistant and display the add App repository dialog with this repository pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Ftlamoureux24%2Fhaos_apps)

#### Manual installation

1. Open Home Assistant.
2. Go to `Settings` > `Apps` > `App store`.
3. Open the menu in the upper-right corner, then select `Repositories`.
4. Add the repository URL:

```text
https://github.com/tlamoureux24/haos_apps
```

5. Select `Add`, then reload the store if necessary.
6. Install the desired App from the store.

### Available Apps

#### MCP Capability Bridge

Experimental foundation for an independent MCP App that turns non-MCP
technical access into strictly bounded capabilities. Version 0.1.0 contains
only the HAOS shell, isolated network surfaces and suite-aligned Ingress UI;
no MCP endpoint or adapter is enabled yet.

Detailed documentation:

- [English documentation](mcp_capability_bridge/README.md)

#### Agent Control Plane

Stable control plane between authenticated agents and one or more configurable
MCP servers. It acts as a deny-by-default MCP application firewall: explicit
administrator configuration is the authorization decision, and only tools and
arguments inside the task's exact capability envelope are exposed to the agent.

Main features:

- generic Streamable HTTP MCP connectors with independent inventories;
- tasks composed from specific tools across one or several connectors;
- optional per-tool fixed arguments, with sensitive values encrypted and
  removed from the schema exposed to the agent;
- unique virtual tools even when several servers publish the same name;
- deny-by-default authorization based on explicit capability selection, without
  a special authorization class merely because an upstream tool reads or
  modifies state;
- manual, scheduled, or authenticated event-driven executions;
- persistent queue, structured reports, retention, and hash-chained audit;
- reversible task and connector archival without losing history;
- bilingual French/English Ingress interface with operational metrics;
- connector secrets remain inside the gateway, can only be replaced through an
  explicit rotation, and are never sent to agents.

Detailed documentation:

- [English documentation](agent_control_plane/README.md)

#### Studio Code Server + Codex

Experimental Home Assistant App providing a persistent development workspace exclusively through authenticated Home Assistant Ingress.

Main features:

- current code-server with an integrated terminal;
- Git, SSH, Home Assistant CLI, Python, and Node.js;
- Codex CLI with ChatGPT subscription OAuth and no required OpenAI Platform API key;
- editor, extensions, and terminals running under an unprivileged account;
- optional official Codex extension installation from the editor Marketplace;
- persistent repositories, SSH keys, Git settings, Codex sessions, editor settings, and extensions;
- automatic Git fetching and optional HA-MCP connection configured from the App;
- Codex execution under an unprivileged account without an inherited Supervisor token;
- administrative access to Home Assistant and App configuration;
- no direct port: access only through Home Assistant and the VPN used to reach it.

Detailed documentation:

- [English documentation](studio_code_server/README.md)

#### Rsync Manager

Home Assistant App with an Ingress interface for configuring, scheduling, testing, and running `rsync` synchronizations.

Main features:

- cron-scheduled `rsync` jobs;
- local or SMB/CIFS sources and destinations;
- dry runs, manual execution, and mount tests;
- `rsync` exclusions and job enable or disable controls;
- latest status and log for each job;
- SMTP email reports;
- import and export of email settings and jobs.

Detailed documentation:

- [English documentation](rsync_manager/README.md)

#### UniFi Autoblock

Local Home Assistant App that receives UniFi Alarm Manager `Threat Detected and Blocked` webhooks, validates IDS/IPS events, and adds the attacker’s public IPv4 address to an existing UniFi `IPV4_ADDRESSES` list.

The App does not create firewall rules. It updates the address list used by an existing UniFi rule, for example an `IP BAN` list applied to a reverse proxy or exposed service.

Main features:

- local webhook endpoint for UniFi Alarm Manager;
- automatically generated URL-token and Bearer-token authentication;
- strict validation of incoming UniFi IDS/IPS events;
- public IPv4 addresses only, excluding local, private, reserved, and IPv6 addresses;
- automatic UniFi site and IPv4 list detection when the configuration allows it;
- JSON backup of the list before each write;
- configurable retention period for addresses managed by the App;
- UniFi API key encrypted in `/data` and then removed from the configuration;
- Home Assistant `unifi_autoblock_ip_banned` event after a confirmed block.

Detailed documentation:

- [English documentation](unifi_autoblock/README.md)

#### UniFi Log Explorer

Standalone Home Assistant App for locally collecting, retaining, and exploring
Traffic Flows and CEF/Syslog events from a UniFi environment.

Main features:

- Traffic Flows collection through the local UniFi API with deduplication and
  reconciliation of late publications;
- UDP Syslog/CEF reception with a strict source-address allowlist;
- interactive 24-hour overview and rankings;
- searchable, filterable, and paginated Traffic Flows and CEF/Syslog explorers;
- standalone authenticated web interface with light and dark themes;
- locally encrypted API key cleared from Home Assistant options;
- configurable retention, cold backups, and secret-free diagnostic exports;
- Settings page with API testing and a read-only Home Assistant configuration summary.

Detailed documentation:

- [English documentation](unifi_log_explorer/README.md)

#### Nginx Proxy Manager

Minimal Home Assistant wrapper around the official Nginx Proxy Manager Docker image. The App preserves all NPM functionality without a fork or modification and adds only the integration required by Supervisor.

Main features:

- official Nginx Proxy Manager image pinned to a stable release;
- App version aligned with NPM as `<NPM version>-<revision>`;
- standard ports 80, 81, and 443 without Home Assistant Ingress;
- persistent NPM data in `/data`;
- persistent certificates and Let’s Encrypt configuration in `/data/letsencrypt`;
- cold Home Assistant backups to preserve SQLite consistency;
- automated detection, validation, and preparation of new NPM releases;
- intentional update installation from Home Assistant.

Detailed documentation:

- [English documentation](nginx_proxy_manager/README.md)

#### Gatus

Home Assistant App based on the official Gatus binary for monitoring network devices and services.

Main features:

- official Gatus release pinned and automatically tracked by the repository;
- ICMP checks run without root or the `NET_RAW` capability;
- editable configuration in the dedicated `addon_config` folder;
- Free Mobile SMS credentials, SMTP settings, and an optional Home Assistant token injected from private options;
- optional publication of Gatus alerts to Home Assistant as `gatus_alert` events;
- no secrets stored in the Gatus file or GitHub repository;
- local interface on port 8080 without Ingress;
- AppArmor profile, internal watchdog, and cold backups;
- initial configuration limited to a local loopback check, with no external address.

Detailed documentation:

- [English documentation](gatus/README.md)

#### AdGuard Home

Minimal Home Assistant App based on the official AdGuard Home Docker image for filtering advertisements, trackers, and unwanted domains at the DNS level.

Main features:

- official AdGuard Home image pinned to a stable release;
- App version aligned as `<AdGuard Home version>-<revision>`;
- TCP/UDP DNS and the administration interface enabled by default;
- separate optional ports for DoH, DoH3, DoT, DoQ, DNSCrypt, and diagnostics;
- bridge networking without `host_network`, Ingress, or Supervisor APIs;
- AdGuard Home administrator authentication independent from Home Assistant;
- non-root execution with AppArmor and minimal privileges;
- persistent configuration, statistics, and logs in `addon_config`;
- cold backups and automated tracking of new official releases;
- DHCP intentionally omitted because it requires layer-2 broadcasts and host networking.

Detailed documentation:

- [English documentation](adguard_home/README.md)

### Requirements

This repository is intended for Home Assistant installations with Supervisor, including:

- Home Assistant OS;
- Home Assistant Supervised.

It is not intended for a standalone Home Assistant Core installation without Supervisor because Home Assistant Apps depend on Supervisor.

### Repository convention

- [Shared internationalization convention](INTERNATIONALIZATION.md#english)

### Updates

Home Assistant monitors App repositories added to the store. When a new App version is published, it appears as an available update in the Home Assistant interface.

If the new version does not appear:

1. Go to `Settings` > `Apps` > `App store`.
2. Open the menu in the upper-right corner.
3. Select `Check for updates` or reload the store.

### Support

For details or help with an App, consult its English documentation first:

- [Agent Control Plane](agent_control_plane/README.md)
- [Rsync Manager](rsync_manager/README.md)
- [Studio Code Server + Codex](studio_code_server/README.md)
- [UniFi Autoblock](unifi_autoblock/README.md)
- [UniFi Log Explorer](unifi_log_explorer/README.md)
- [Nginx Proxy Manager](nginx_proxy_manager/README.md)
- [Gatus](gatus/README.md)
- [AdGuard Home](adguard_home/README.md)
