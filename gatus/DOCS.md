# Gatus

## Français

Cette App utilise une version stable épinglée du binaire officiel Gatus et
stocke sa configuration dans le dossier addon_config dédié.

### Configuration privée

Les identifiants SMS Free Mobile, les paramètres SMTP et l'option facultative
Home Assistant sont saisis dans l'onglet Configuration de l'App. Le lanceur les
injecte comme variables d'environnement ; ils ne figurent jamais directement
dans le fichier Gatus.

Options facultatives, à renseigner uniquement pour les fournisseurs activés :

- sms_user et sms_password ;
- email_from, email_username et email_password ;
- email_host, email_port et email_to ;
- homeassistant_token, uniquement pour le fournisseur `homeassistant` de Gatus.

L'App peut démarrer sans aucune de ces options lorsqu'aucun fournisseur
d'alerte correspondant n'est activé dans config.yaml. L'option Home Assistant
n'active rien à elle seule : elle rend seulement la variable
`GATUS_HOMEASSISTANT_TOKEN` disponible pour une configuration Gatus qui choisit
de l'utiliser.

Après une modification de ces options, redémarrez l'App.

### Alertes Home Assistant facultatives

Le fournisseur natif `homeassistant` de Gatus peut publier des événements
`gatus_alert` dans Home Assistant. Il reste entièrement facultatif : ajoutez-le
dans `alerting` et avec `type: homeassistant` uniquement sur les endpoints qui
doivent l'utiliser. La configuration initiale continue de laisser tous les
fournisseurs d'alerte désactivés.

### Fichier Gatus

Au premier démarrage, le modèle est copié vers :

    /addon_configs/<identifiant_du_dépôt>_gatus/config.yaml

Les modifications du fichier sont rechargées automatiquement. Une mise à jour
de l'App ne l'écrase jamais. Gatus exigeant au moins un endpoint ou une suite,
le squelette contient uniquement un contrôle loopback local sur `127.0.0.1` et
aucune donnée provenant du réseau de l'utilisateur.

### Accès

    http://ADRESSE_IP_HOME_ASSISTANT:8080

Le port 8080 doit rester local ou accessible par VPN. Il n'y a pas d'Ingress ni
de raccourci Web UI.

### Historique SQLite facultatif

    storage:
      type: sqlite
      path: /data/gatus/gatus.db

## English

This App uses a pinned stable release of the official Gatus binary and stores
its configuration in the dedicated addon_config folder.

### Private configuration

Free Mobile SMS credentials, SMTP settings and the optional Home Assistant
option are entered in the App Configuration tab. The launcher injects them as
environment variables; they never need to appear directly in the Gatus file.

Optional options, required only for enabled providers:

- sms_user and sms_password;
- email_from, email_username and email_password;
- email_host, email_port and email_to;
- homeassistant_token, only for Gatus' `homeassistant` provider.

The App can start without any of these options when the corresponding alert
providers are disabled in config.yaml. The Home Assistant option does not
enable anything by itself: it only makes `GATUS_HOMEASSISTANT_TOKEN` available
to a Gatus configuration that chooses to use it.

Restart the App after changing these options.

### Optional Home Assistant alerts

Gatus' native `homeassistant` provider can publish `gatus_alert` events to Home
Assistant. It remains fully optional: add it under `alerting` and use
`type: homeassistant` only on endpoints that should send those events. The
initial configuration continues to keep every alert provider disabled.

### Gatus file

On first start, the template is copied to:

    /addon_configs/<repository_identifier>_gatus/config.yaml

File changes are reloaded automatically. App updates never overwrite it.
Because Gatus requires at least one endpoint or suite, the initial skeleton
contains only a local loopback check on `127.0.0.1` and no user network data.

### Access

    http://HOME_ASSISTANT_IP:8080

Port 8080 should remain local or accessible through VPN. There is no Ingress or
Web UI shortcut.

### Optional SQLite history

    storage:
      type: sqlite
      path: /data/gatus/gatus.db
