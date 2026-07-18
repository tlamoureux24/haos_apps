# Gatus

## Français

Cette App utilise une version stable épinglée du binaire officiel Gatus et
stocke sa configuration dans le dossier addon_config dédié.

### Configuration privée

Les identifiants SMS Free Mobile et les paramètres SMTP sont saisis dans
l'onglet Configuration de l'App. Le lanceur les injecte comme variables
d'environnement ; ils ne figurent jamais dans le fichier Gatus.

Options requises :

- sms_user et sms_password ;
- email_from, email_username et email_password ;
- email_host, email_port et email_to.

Après une modification de ces options, redémarrez l'App.

### Fichier Gatus

Au premier démarrage, le modèle est copié vers :

    /addon_configs/<identifiant_du_dépôt>_gatus/config.yaml

Les modifications du fichier sont rechargées automatiquement. Une mise à jour
de l'App ne l'écrase jamais. Le squelette initial contient `endpoints: []` :
aucun nom d'équipement ni aucune adresse réseau ne sont fournis par l'App.

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

Free Mobile SMS credentials and SMTP settings are entered in the App
Configuration tab. The launcher injects them as environment variables; they
never appear in the Gatus file.

Required options:

- sms_user and sms_password;
- email_from, email_username and email_password;
- email_host, email_port and email_to.

Restart the App after changing these options.

### Gatus file

On first start, the template is copied to:

    /addon_configs/<repository_identifier>_gatus/config.yaml

File changes are reloaded automatically. App updates never overwrite it.
The initial skeleton contains `endpoints: []`: the App ships no device name or
network address.

### Access

    http://HOME_ASSISTANT_IP:8080

Port 8080 should remain local or accessible through VPN. There is no Ingress or
Web UI shortcut.

### Optional SQLite history

    storage:
      type: sqlite
      path: /data/gatus/gatus.db
