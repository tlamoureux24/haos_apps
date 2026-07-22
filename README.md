# Thibs's Home Assistant Apps

Depot d'Apps pour Home Assistant OS / Supervisor.

## Installation Du Repository

### Installation Avec My Home Assistant

[![Open your Home Assistant instance and show the add add-on repository dialog with this repository pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Ftlamoureux24%2Fhaos_apps)

### Installation Manuelle

1. Ouvrir Home Assistant.
2. Aller dans `Paramètres` > `Modules complémentaires` > `Boutique des modules complémentaires`.
3. Ouvrir le menu en haut a droite, puis `Dépôts`.
4. Ajouter l'URL du repository:

```text
https://github.com/tlamoureux24/haos_apps
```

5. Cliquer sur `Ajouter`, puis recharger la boutique si necessaire.
6. Installer l'App voulue depuis la boutique.

## Apps Disponibles

### Rsync Manager

App Home Assistant avec interface Ingress pour configurer, planifier, tester et lancer des synchronisations `rsync`.

Fonctionnalités principales:

- jobs rsync planifies par cron;
- sources et destinations locales ou SMB/CIFS;
- mode dry-run;
- execution manuelle;
- test des montages;
- exclusions rsync;
- activation/desactivation de jobs;
- dernier statut et dernier log par job;
- rapports email SMTP;
- import/export des configurations email et jobs.

Documentation détaillée:

- [Documentation française](rsync_manager/README.fr.md)
- [English documentation](rsync_manager/README.md)

### UniFi Autoblock

App Home Assistant locale qui reçoit les webhooks UniFi Alarm Manager `Threat Detected and Blocked`, valide les événements IDS/IPS et ajoute l'IP source publique de l'attaquant dans une liste UniFi `IPV4_ADDRESSES` existante.

L'application ne crée pas de règle firewall elle-même. Elle met à jour la liste d'IP utilisée par votre règle firewall UniFi existante, par exemple une liste `IP BAN` appliquée au reverse proxy ou à un service exposé.

Fonctionnalités principales:

- endpoint webhook local pour UniFi Alarm Manager;
- authentification webhook par token d'URL et Bearer token générés automatiquement;
- source webhook acceptée automatiquement depuis l'hôte configuré dans `unifi_base_url`;
- mode simulation `dry_run` activé par défaut;
- validation stricte des événements UniFi IDS/IPS entrants;
- ajout d'IPv4 publiques uniquement, avec exclusion automatique des IP locales, privées, réservées et IPv6;
- détection automatique du site UniFi et de la liste IPv4 quand l'installation est simple;
- mise à jour d'une liste UniFi `IPV4_ADDRESSES` existante;
- sauvegarde JSON de la liste avant chaque écriture dans `/data/last_traffic_matching_list_backup.json`;
- TTL configurable, 30 jours par défaut, appliqué seulement aux IP gérées par l'application;
- clé API UniFi saisie comme mot de passe, chiffrée dans `/data`, puis retirée de la configuration;
- clé locale de déchiffrement exclue des sauvegardes Home Assistant;
- événement Home Assistant `unifi_autoblock_ip_banned` après bannissement confirmé, utilisable dans les automatisations.

Documentation détaillée:

- [Documentation française](unifi_autoblock/README.fr.md)
- [English documentation](unifi_autoblock/README.md)

### Nginx Proxy Manager

Enveloppe Home Assistant minimale autour de l'image Docker officielle Nginx
Proxy Manager. L'App conserve toutes les fonctionnalités NPM sans fork ni
modification et ajoute uniquement l'intégration nécessaire au Supervisor.

Fonctionnalités principales:

- image Nginx Proxy Manager officielle, épinglée sur une version stable ;
- version de l'App alignée sur NPM au format `<version NPM>-<révision>` ;
- ports standards 80, 81 et 443, sans Ingress Home Assistant ;
- données NPM persistées dans `/data` ;
- certificats et configuration Let's Encrypt persistés dans `/data/letsencrypt` ;
- sauvegarde Home Assistant à froid pour garantir la cohérence de SQLite ;
- détection, validation et préparation automatiques des nouvelles versions NPM ;
- installation volontaire des mises à jour depuis Home Assistant.

Documentation détaillée:

- [Documentation française](nginx_proxy_manager/README.fr.md)
- [English documentation](nginx_proxy_manager/README.md)

### Gatus

App Home Assistant basée sur le binaire officiel Gatus pour surveiller les
équipements et services du réseau.

Fonctionnalités principales:

- version officielle Gatus épinglée et mise à jour automatiquement dans le dépôt ;
- contrôles ICMP exécutés sans root et sans capacité NET_RAW ;
- configuration éditable dans le dossier addon_config dédié ;
- identifiants SMS Free Mobile et paramètres SMTP injectés depuis les options privées ;
- aucun secret dans le fichier Gatus ou dans le dépôt GitHub ;
- interface locale sur le port 8080, sans Ingress ;
- profil AppArmor, watchdog interne et sauvegarde à froid ;
- squelette initial limité à un contrôle loopback local, sans adresse externe.

Documentation détaillée:

- [Documentation française](gatus/README.fr.md)
- [English documentation](gatus/README.md)

### AdGuard Home

App Home Assistant minimale basée sur l'image Docker officielle AdGuard Home
pour filtrer les publicités, traqueurs et domaines indésirables au niveau DNS.

Fonctionnalités principales :

- image officielle AdGuard Home épinglée sur une version stable ;
- version de l'App alignée au format `<version AdGuard Home>-<révision>` ;
- DNS TCP/UDP et interface d'administration activés par défaut ;
- ports DoH, DoH3, DoT, DoQ, DNSCrypt et diagnostic disponibles séparément ;
- réseau bridge sans `host_network`, Ingress ou API Supervisor ;
- authentification administrateur AdGuard Home indépendante de Home Assistant ;
- exécution non-root avec AppArmor et privilèges minimaux ;
- configuration, statistiques et journaux persistés dans `addon_config` ;
- sauvegarde à froid et suivi automatisé des nouvelles versions officielles ;
- DHCP volontairement absent car il nécessite les broadcasts de niveau 2 et le réseau hôte.

Documentation détaillée :

- [Documentation française](adguard_home/README.fr.md)
- [English documentation](adguard_home/README.md)

## Prerequis

Ce repository est destine aux installations Home Assistant avec Supervisor, par exemple:

- Home Assistant OS;
- Home Assistant Supervised.

Il n'est pas destine a une installation Home Assistant Core seule sans Supervisor, car les Apps Home Assistant dependent du Supervisor.

## Mise A Jour

Home Assistant surveille les depots d'Apps ajoutes a la boutique. Si une nouvelle version d'une App est publiee, elle apparaitra comme mise à jour disponible dans l'interface Home Assistant.

Si la nouvelle version n'apparait pas:

1. Aller dans `Paramètres` > `Modules complémentaires` > `Boutique des modules complémentaires`.
2. Ouvrir le menu en haut a droite.
3. Cliquer sur `Rechercher les mises a jour` ou recharger la boutique.

## Support

Pour comprendre le fonctionnement de chaque App, consultez d'abord son README dedie.

Pour Rsync Manager:

[rsync_manager/README.fr.md](rsync_manager/README.fr.md)

Pour UniFi Autoblock:

[unifi_autoblock/README.md](unifi_autoblock/README.md)

Pour Nginx Proxy Manager:

[nginx_proxy_manager/README.fr.md](nginx_proxy_manager/README.fr.md)

Pour Gatus:

[gatus/README.fr.md](gatus/README.fr.md)

Pour AdGuard Home:

[adguard_home/README.fr.md](adguard_home/README.fr.md)
