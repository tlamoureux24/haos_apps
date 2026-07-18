# Rsync Manager

## Français

Rsync Manager permet de créer, planifier, tester et surveiller des
synchronisations locales ou SMB/CIFS depuis une interface Ingress protégée par
Home Assistant.

L'interface accepte les chemins locaux, mais aucun dossier Home Assistant n'est
mappe par defaut. Pour utiliser des jobs locaux, le proprietaire du depot doit
decommenter uniquement les mappings necessaires dans `config.yaml`, puis
reconstruire ou reinstaller l'App :

```yaml
map:
  - type: share
    read_only: false
  - type: media
    read_only: false
  - type: backup
    read_only: false
```

Commencez toujours par `Tester montages`, puis `Simuler`, avant de lancer une
nouvelle synchronisation réelle. L'option rsync `--delete` est active : la
destination devient un miroir de la source.

Les identifiants SMB et SMTP sont enregistrés dans le volume privé `/data` avec
des permissions `0600`. Ils restent toutefois présents en clair dans les
exports téléchargés et dans les sauvegardes Home Assistant : conservez-les dans
un emplacement sûr.

Les rapports SMTP sont facultatifs. Les certificats TLS du serveur SMTP sont
vérifiés. Le privilège `SYS_ADMIN` est requis uniquement pour monter et démonter
les partages CIFS.

[Documentation française complète](https://github.com/tlamoureux24/haos_apps/blob/main/rsync_manager/README.fr.md)

## English

Rsync Manager creates, schedules, tests and monitors local or SMB/CIFS
synchronizations from a Home Assistant-authenticated Ingress interface.

The interface accepts local paths, but no Home Assistant folder is mapped by
default. To use local jobs, the repository owner must uncomment only the
required mappings in `config.yaml`, then rebuild or reinstall the App:

```yaml
map:
  - type: share
    read_only: false
  - type: media
    read_only: false
  - type: backup
    read_only: false
```

Always use `Test mounts` and then `Dry run` before the first real
synchronization. Rsync's `--delete` option is enabled, so the destination is a
mirror of the source.

SMB and SMTP credentials are stored in the private `/data` volume with mode
`0600`. Downloaded exports and Home Assistant backups still contain them in
clear text and must be stored securely.

SMTP reports are optional and SMTP TLS certificates are verified. `SYS_ADMIN`
is required only to mount and unmount CIFS shares.

[Full English documentation](https://github.com/tlamoureux24/haos_apps/blob/main/rsync_manager/README.md)
