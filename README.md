# Thibs's Home Assistant Apps

Repository d'addons Home Assistant OS / Supervisor.

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
6. Installer l'addon voulu depuis la boutique.

## Addons Disponibles

### Rsync Manager

Addon Home Assistant avec interface Ingress pour configurer, planifier, tester et lancer des synchronisations `rsync`.

Fonctionnalites principales:

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

Documentation detaillee:

[rsync_manager/README.md](rsync_manager/README.md)

## Prerequis

Ce repository est destine aux installations Home Assistant avec Supervisor, par exemple:

- Home Assistant OS;
- Home Assistant Supervised.

Il n'est pas destine a une installation Home Assistant Core seule sans Supervisor, car les addons Home Assistant dependent du Supervisor.

## Mise A Jour

Home Assistant surveille les repositories d'addons ajoutes a la boutique. Si une nouvelle version d'un addon est publiee, elle apparaitra comme mise a jour disponible dans l'interface Home Assistant.

Si la nouvelle version n'apparait pas:

1. Aller dans `Paramètres` > `Modules complémentaires` > `Boutique des modules complémentaires`.
2. Ouvrir le menu en haut a droite.
3. Cliquer sur `Rechercher les mises a jour` ou recharger la boutique.

## Support

Pour comprendre le fonctionnement de chaque addon, consultez d'abord son README dedie.

Pour Rsync Manager:

[rsync_manager/README.md](rsync_manager/README.md)
