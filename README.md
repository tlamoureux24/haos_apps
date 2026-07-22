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
- identifiants SMS Free Mobile et paramètres SMTP injectés depuis les options privées ;
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

### Mises à jour

Home Assistant surveille les dépôts d’Apps ajoutés à la boutique. Lorsqu’une nouvelle version d’une App est publiée, elle apparaît comme mise à jour disponible dans l’interface Home Assistant.

Si la nouvelle version n’apparaît pas :

1. Aller dans `Paramètres` > `Modules complémentaires` > `Boutique des modules complémentaires`.
2. Ouvrir le menu en haut à droite.
3. Sélectionner `Rechercher les mises à jour` ou recharger la boutique.

### Support

Pour comprendre le fonctionnement d’une App ou obtenir de l’aide, consulter d’abord sa documentation française :

- [Rsync Manager](rsync_manager/README.fr.md)
- [UniFi Autoblock](unifi_autoblock/README.fr.md)
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
- Free Mobile SMS credentials and SMTP settings injected from private options;
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

### Updates

Home Assistant monitors App repositories added to the store. When a new App version is published, it appears as an available update in the Home Assistant interface.

If the new version does not appear:

1. Go to `Settings` > `Apps` > `App store`.
2. Open the menu in the upper-right corner.
3. Select `Check for updates` or reload the store.

### Support

For details or help with an App, consult its English documentation first:

- [Rsync Manager](rsync_manager/README.md)
- [UniFi Autoblock](unifi_autoblock/README.md)
- [Nginx Proxy Manager](nginx_proxy_manager/README.md)
- [Gatus](gatus/README.md)
- [AdGuard Home](adguard_home/README.md)
