# Rsync Manager

Rsync Manager est un addon Home Assistant qui permet de configurer, planifier, tester et lancer des synchronisations `rsync` depuis une interface web Ingress.

Il sert principalement a copier ou synchroniser des dossiers entre:

- des chemins locaux exposes au conteneur par Home Assistant (`/share`, `/media`, `/backup`, etc.);
- des partages reseau SMB/CIFS en source;
- des partages reseau SMB/CIFS en destination;
- un melange local -> CIFS, CIFS -> local, local -> local ou CIFS -> CIFS.

L'addon permet aussi de programmer les jobs avec une expression cron, de lancer un dry-run manuel, de lancer une execution reelle, de tester les montages, d'exclure des fichiers/dossiers, d'envoyer un rapport email et de consulter le dernier statut/log de chaque job.

## Fonctionnement General

L'addon utilise:

- `rsync` pour synchroniser les fichiers;
- `crond` BusyBox/Alpine pour la planification;
- `cifs-utils` pour monter les partages SMB/CIFS;
- `msmtp` pour envoyer les emails;
- `lighttpd` pour l'interface web Ingress;
- `jq` pour lire et ecrire les fichiers JSON.

Les fichiers persistants sont stockes dans `/data`:

- `/data/jobs.json`: liste des jobs rsync;
- `/data/config.json`: configuration SMTP/email;
- `/data/status.json`: dernier statut connu de chaque job;
- `/data/logs/<job_id>.log`: dernier log complet de chaque job.

Chaque job possede un identifiant stable de type `job_...`. Cet identifiant est utilise par l'interface, le runner, le cron, les statuts et les logs. Cela evite de confondre les jobs quand un job est supprime ou quand l'ordre de la liste change.

Quand les jobs sont sauvegardes depuis l'interface, l'addon regenere automatiquement le fichier cron:

```sh
/var/spool/cron/crontabs/root
```

Puis il arrete `crond`. Comme `crond` est gere par s6, il est relance automatiquement. Cela permet a Alpine/BusyBox de reprendre proprement les nouvelles planifications.

Les executions manuelles depuis l'interface (`Tester montages`, `Simuler` et `Lancer`) passent par un service interne appele runner. L'interface web depose une demande d'execution dans une file temporaire, puis le runner execute le job. Cela evite de lancer les montages CIFS directement depuis le processus CGI de l'interface web.

## Installation

Placez le dossier de l'addon dans le repertoire des addons locaux Home Assistant, puis reconstruisez/installez l'addon depuis l'interface Home Assistant.

L'addon utilise Ingress, il apparait donc directement dans Home Assistant avec le panneau:

```text
Rsync Manager
```

## Permissions Home Assistant

Les chemins locaux accessibles par l'addon sont controles par la directive `map` dans `config.yaml`.

Exemple:

```yaml
map:
  - config:rw
  - share:rw
  - media:rw
  - backup:rw
  - addons:ro
  - ssl:ro
```

Dans le conteneur, ces dossiers sont accessibles via:

```text
/config
/share
/media
/backup
/addons
/ssl
```

### Synchronisation Avec AppArmor

Quand AppArmor est active, les dossiers exposes a l'addon doivent etre declares a deux endroits:

- dans `config.yaml`, avec `map`, pour demander a Home Assistant de monter le dossier dans le conteneur;
- dans `apparmor.txt`, pour autoriser le processus de l'addon a lire ou ecrire dans ce chemin.

Les deux declarations doivent rester coherentes. Si un dossier est monte en lecture/ecriture dans `config.yaml`, mais autorise seulement en lecture dans `apparmor.txt`, l'ecriture sera bloquee. A l'inverse, si `apparmor.txt` autorise l'ecriture mais que `config.yaml` monte le dossier en lecture seule, l'ecriture restera impossible.

Exemple correspondant au `map` ci-dessus:

```apparmor
/config/** rw,
/share/** rw,
/media/** rw,
/backup/** rw,
/addons/** r,
/ssl/** r,
```

Regle pratique:

- `config.yaml` dit quels dossiers sont montes dans le conteneur;
- `apparmor.txt` dit ce que l'addon a le droit de faire sur ces dossiers.

Quand vous ajoutez, retirez ou changez un dossier dans `map`, mettez aussi a jour la section correspondante dans `apparmor.txt`.

Pour utiliser SMB/CIFS, l'addon a besoin de privileges permettant les montages reseau:

```yaml
privileged:
  - SYS_ADMIN
  - DAC_READ_SEARCH
```

## Onglet JOBS

L'onglet `JOBS` permet de creer, modifier, sauvegarder, tester et executer les synchronisations.

Chaque job contient:

- un identifiant stable `id` genere automatiquement;
- un nom;
- un switch `Actif` / `Desactive`;
- une expression cron;
- une source;
- une destination;
- une liste d'exclusions rsync;
- un dernier statut;
- un bouton `Voir dernier log`;
- des boutons `Tester montages`, `Simuler`, `Lancer` et supprimer.

### Activer Ou Desactiver Un Job

Le switch `Actif` controle uniquement la planification cron.

- `Actif`: le job est ajoute au crontab genere.
- `Desactive`: le job reste dans la configuration, mais il est ignore par le cron.

Les actions manuelles restent disponibles meme si le job est desactive. Vous pouvez donc tester les montages, simuler ou lancer ponctuellement un job desactive.

### Boutons

`Sauvegarder les Jobs` enregistre `/data/jobs.json` et regenere la planification cron.

`Actualiser` recharge les jobs et les statuts depuis l'addon.

`Tester montages` monte la source et la destination si elles sont en SMB/CIFS, verifie que les chemins sont accessibles, teste l'ecriture sur la destination, puis demonte les partages. Cette action ne lance pas `rsync`.

`Simuler` lance un dry-run rsync. Aucune modification n'est appliquee. C'est utile pour verifier ce qui serait copie ou supprime.

`Lancer` execute reellement le job.

## Statuts Et Derniers Logs

Chaque execution met a jour le dernier statut du job dans `/data/status.json` et le dernier log complet dans `/data/logs/<job_id>.log`.

Les statuts visibles dans l'interface sont:

- `Jamais execute`: aucun statut disponible pour ce job;
- `Succes`: execution ou dry-run termine sans erreur;
- `Montages OK`: test de montage reussi;
- `Echec`: `rsync` a retourne une erreur;
- `Erreur montage`: montage, acces source ou ecriture destination impossible;
- `Desactive`: le cron ignore ce job.

Le statut affiche aussi, quand disponible:

- date/heure de derniere execution;
- declenchement (`manuel` ou `cron`);
- mode (`run`, `dry-run` ou `test montages`);
- duree;
- resume rsync (`envoye`, `recu`, `total`).

Le bouton `Voir dernier log` affiche le dernier log persistant du job dans une fenetre de l'interface.

## Exclusions Rsync

Chaque job peut definir des exclusions, une regle par ligne.

Exemples:

```text
cache/
*.tmp
@eaDir/
#recycle/
```

Ces exclusions sont appliquees aux actions `Simuler` et `Lancer` via `--exclude-from`. Elles ne sont pas utilisees par `Tester montages`, car ce test ne lance pas `rsync`.

## Modes Source Et Destination

La source et la destination sont independantes. Chacune peut etre en mode `Local` ou `SMB/CIFS`.

Cela permet par exemple:

- local -> local;
- local -> SMB/CIFS;
- SMB/CIFS -> local;
- SMB/CIFS -> SMB/CIFS, avec deux serveurs differents et deux identifiants differents.

## Mode Local

En mode `Local`, un simple chemin suffit.

Exemples:

```text
/share/mosquitto
/share/copymosquitto
/media/photos
/backup/archives
```

Le chemin doit exister dans le conteneur et etre autorise par `map` dans `config.yaml`.

## Mode SMB/CIFS

En mode `SMB/CIFS`, chaque cote possede ses propres champs:

- `Adresse IP ou nom`: adresse IP ou nom DNS/NetBIOS du serveur;
- `Partage reseau`: nom du partage;
- `Sous-dossier dans le partage`: chemin interne optionnel dans le partage;
- `Login`: utilisateur SMB;
- `Mot de passe`: mot de passe SMB;
- `Domaine/Workgroup`: optionnel, utile si le serveur SMB impose un domaine ou un workgroup;
- `Version SMB`: version du protocole a utiliser;
- `Securite`: mode d'authentification CIFS;
- `Options CIFS avancees`: options supplementaires passees a `mount.cifs`.

Par defaut, l'addon ajoute:

```text
noperm,noserverino,nounix
```

Ces options evitent plusieurs problemes frequents avec les montages CIFS depuis un conteneur Home Assistant:

- `noperm`: laisse le serveur SMB gerer les droits plutot que le client Linux;
- `noserverino`: evite certains problemes d'inodes exposes par le serveur;
- `nounix`: desactive les extensions Unix CIFS qui peuvent perturber certains serveurs Samba/NAS.

Il ne faut pas mettre le chemin complet dans le champ partage. CIFS monte uniquement le couple `//serveur/partage`. Le sous-dossier est ensuite utilise par `rsync` apres le montage.

Exemple correct:

```text
Adresse IP ou nom:
192.168.1.20

Partage reseau:
Documents

Sous-dossier dans le partage:
Archives/2026
```

L'addon construira automatiquement:

```text
//192.168.1.20/Documents
```

Puis utilisera comme chemin rsync:

```text
/mnt/.../Archives/2026
```

## Planification Cron

Chaque job possede une expression cron au format 5 champs:

```text
minute heure jour_du_mois mois jour_de_la_semaine
```

Exemples utiles:

```cron
* * * * *
```

Toutes les minutes.

```cron
*/2 * * * *
```

Toutes les 2 minutes.

```cron
0 * * * *
```

Toutes les heures, a la minute 0.

```cron
0 3 * * *
```

Tous les jours a 03:00.

```cron
30 2 * * 1
```

Tous les lundis a 02:30.

```cron
0 4 1 * *
```

Le 1er jour de chaque mois a 04:00.

Apres chaque sauvegarde des jobs, l'addon:

1. ecrit `/data/jobs.json`;
2. normalise les jobs (`id`, `enabled`, `excludes`);
3. regenere `/var/spool/cron/crontabs/root`;
4. ignore les jobs desactives;
5. arrete `crond`;
6. laisse s6 relancer `crond`.

Dans les logs, vous devriez voir:

```text
[CRON] Generation des regles depuis /data/jobs.json
[CRON] 1 regle(s) installee(s) dans /var/spool/cron/crontabs/root.
[CRON] crond arrete apres regeneration, s6 va le relancer.
```

## Onglet SMTP

L'onglet `SMTP` permet de configurer l'envoi des rapports email.

Champs disponibles:

- activer/desactiver les emails;
- serveur SMTP;
- port;
- authentification;
- utilisateur;
- mot de passe;
- TLS actif;
- STARTTLS;
- expediteur;
- destinataire.

Un bouton `Envoyer un Test` permet de verifier la configuration.

### Exemple Gmail

Pour Gmail avec le port 587:

```text
Serveur: smtp.gmail.com
Port: 587
Authentification: Oui
Utilisateur: votre.adresse@gmail.com
Mot de passe: mot de passe d'application Google
TLS actif: Oui
STARTTLS: Oui
Expediteur: votre.adresse@gmail.com
Destinataire: votre.adresse@gmail.com
```

Pour Gmail, utilisez un mot de passe d'application Google. Le mot de passe normal du compte ne fonctionne generalement pas.

### Quand Les Emails Sont Envoyes

Les emails sont envoyes apres les executions reelles (`run`), avec le resultat du job.

Les dry-runs manuels et les tests de montage ecrivent un statut/log, mais n'envoient pas de rapport email.

## Onglet GESTION

L'onglet `GESTION` permet d'importer et d'exporter les configurations depuis le navigateur.

Boutons disponibles:

- `Export config email`: telecharge la configuration SMTP/email;
- `Export config jobs`: telecharge les jobs;
- `Import config email`: importe une configuration SMTP/email JSON;
- `Import config jobs`: importe une liste de jobs JSON.

Les exports contiennent les mots de passe SMTP et SMB/CIFS en clair, car ces valeurs sont necessaires au fonctionnement de l'addon. Conservez ces fichiers dans un emplacement sur.

Lors de l'import des jobs, l'addon normalise automatiquement les champs manquants:

- `id`: genere si absent ou duplique;
- `enabled`: `true` par defaut;
- `excludes`: liste vide par defaut.
- `rsync_inplace`: active par defaut pour une cible SMB/CIFS.
- `rsync_smb_permissions`: active par defaut pour une cible SMB/CIFS.

Apres import des jobs, la planification cron est regeneree immediatement.

## Logs

Les logs utiles sont visibles dans le journal de l'addon Home Assistant et, pour chaque job, dans l'interface via `Voir dernier log`.

Prefixes importants dans le journal de l'addon:

```text
[API]
```

Appels de l'interface web vers l'addon.

```text
[CRON]
```

Generation et rechargement de la planification.

```text
[CIFS]
```

Montage des partages SMB/CIFS.

```text
[RUNNER]
```

Execution des jobs demandes par l'interface web.

```text
[EMAIL]
```

Envoi des emails via SMTP.

Exemple d'execution:

```text
--- DEMARRAGE : Backup (id job_..., Mode run, Declenchement manual) ---
sending incremental file list
...
[EMAIL] Message envoye avec succes.
```

## Verifications Utiles Dans Le Conteneur

Afficher les jobs:

```sh
cat /data/jobs.json
```

Afficher la configuration SMTP:

```sh
cat /data/config.json
```

Afficher les statuts:

```sh
cat /data/status.json
```

Afficher le dernier log d'un job:

```sh
cat /data/logs/job_xxx.log
```

Afficher le crontab genere:

```sh
cat /var/spool/cron/crontabs/root
```

Verifier que `crond` tourne:

```sh
pidof crond
```

Lancer un job manuellement depuis le conteneur:

```sh
/usr/local/bin/rsync_manager.sh mount_test job_xxx manual
/usr/local/bin/rsync_manager.sh dry job_xxx manual
/usr/local/bin/rsync_manager.sh run job_xxx manual
```

Regenerer manuellement le cron:

```sh
/usr/local/bin/rsync_cron.sh
```

## Depannage

### Le Job Ne S'execute Pas Automatiquement

Verifiez:

- que le job a ete sauvegarde;
- que le job est actif;
- que l'expression cron contient bien 5 champs;
- que `/var/spool/cron/crontabs/root` contient la ligne du job;
- que les logs contiennent `[CRON] crond arrete apres regeneration, s6 va le relancer.`;
- que `crond` tourne avec `pidof crond`.

### Le Dry-Run Fonctionne Mais Pas Le Cron

Le job lui-meme est probablement correct. Regardez plutot:

- le switch `Actif`;
- le contenu de `/var/spool/cron/crontabs/root`;
- les logs `[CRON]`;
- l'expression cron.

### Le Test Montages Echoue

Verifiez:

- adresse IP ou nom du serveur;
- nom du partage sans `//serveur/`;
- sous-dossier separe du nom du partage;
- login et mot de passe;
- domaine/workgroup si le serveur en demande un;
- droits du compte SMB;
- droits d'ecriture sur la destination;
- acces reseau depuis Home Assistant;
- version SMB supportee par le serveur.

### Le Montage CIFS Echoue

Verifiez:

- adresse IP ou nom du serveur;
- nom du partage sans `//serveur/`;
- sous-dossier separe du nom du partage;
- login et mot de passe;
- domaine/workgroup si le serveur en demande un;
- droits du compte SMB;
- acces reseau depuis Home Assistant;
- version SMB supportee par le serveur.

L'addon permet de choisir la version SMB:

```text
SMB 3.1.1
SMB 3.0
SMB 2.1
SMB 2.0
SMB 1.0
```

Si vous obtenez `Permission denied` alors que le compte est correct, essayez d'abord:

- `SMB 3.0` avec `sec=ntlmssp`;
- `SMB 2.1` avec `sec=ntlmssp`;
- renseigner `WORKGROUP` ou le domaine reel du serveur;
- utiliser les options CIFS avancees `noserverino,nounix`;
- verifier que le nom du partage est exactement celui expose par le serveur SMB.

### Les Exclusions Ne S'appliquent Pas

Verifiez:

- une exclusion par ligne;
- pas de guillemets autour des motifs;
- que le motif correspond au chemin relatif vu par `rsync`;
- le dernier log du job, qui indique si des exclusions sont actives.

### Gmail Refuse L'envoi

Verifiez:

- `TLS actif = Oui`;
- `STARTTLS = Oui`;
- port `587`;
- mot de passe d'application Google;
- expediteur coherent avec le compte Gmail.

### Les Logs Cron Affichent Beaucoup De Bruit

L'addon lance `crond` avec un niveau de log reduit pour eviter les traces internes BusyBox.

Les logs utiles de l'addon restent visibles via les prefixes `[API]`, `[CRON]`, `[CIFS]`, `[RUNNER]` et `[EMAIL]`.

## Notes Sur Rsync

L'addon utilise actuellement:

```sh
rsync -avh --delete
```

En dry-run, il ajoute:

```sh
--dry-run
```

Quand des exclusions sont definies, il ajoute:

```sh
--exclude-from=<fichier temporaire>
```

Quand la destination est SMB/CIFS, l'addon active aussi par defaut:

```sh
--inplace
--no-perms --no-owner --no-group --chmod=ugo=rwX
```

Cette option evite les fichiers temporaires caches crees par rsync dans la destination, de la forme `.nom-du-fichier.XXXXXX`. Ces noms sont normaux: ils ne doivent pas exister dans la source. Sur certains partages SMB/CIFS, leur creation peut echouer avec `mkstemp ... No such file or directory`.

Les options de permissions SMB evitent qu'un fichier source en lecture seule rende la copie destination non reinscriptible lors du prochain passage avec `--inplace`.

Attention: `--delete` supprime dans la destination les fichiers qui n'existent plus dans la source. Utilisez `Simuler` avant un nouveau job ou apres une modification importante.
