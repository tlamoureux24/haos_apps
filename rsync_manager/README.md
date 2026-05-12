# Rsync Manager

Rsync Manager est un addon Home Assistant pour creer, planifier, tester et lancer des synchronisations `rsync` depuis une interface web Ingress.

Il permet de synchroniser:

- un chemin local vers un autre chemin local;
- un chemin local vers un partage SMB/CIFS;
- un partage SMB/CIFS vers un chemin local;
- un partage SMB/CIFS vers un autre partage SMB/CIFS.

L'interface sert aussi a tester les montages, lancer une simulation, executer un job, consulter le dernier statut, afficher le dernier log, configurer les emails SMTP et importer/exporter la configuration.

## Installation

L'installation se fait depuis le depot GitHub Home Assistant:

```text
https://github.com/tlamoureux24/haos_apps
```

Dans Home Assistant:

1. Ouvrir `Parametres` > `Modules complementaires` > `Boutique des modules complementaires`.
2. Ouvrir le menu en haut a droite.
3. Choisir `Depots`.
4. Ajouter l'URL du depot:

```text
https://github.com/tlamoureux24/haos_apps
```

5. Rechercher puis installer `Rsync Manager`.
6. Demarrer l'addon.
7. Ouvrir l'interface depuis le panneau `Rsync Manager`.

L'addon utilise Ingress, il s'ouvre donc directement dans Home Assistant.

## Interface

L'interface contient trois onglets:

- `JOBS`: liste, creation, edition, execution et logs des jobs rsync;
- `SMTP`: configuration de l'envoi des rapports email;
- `GESTION`: import/export des configurations.

Un pied de page permet de basculer entre mode clair et mode sombre. Le choix du theme est conserve dans le navigateur. Le lien GitHub a droite pointe vers le dossier de l'addon dans le depot.

## Onglet JOBS

L'onglet `JOBS` affiche uniquement la liste des jobs existants. Si aucun job n'existe, la liste est vide.

Chaque carte de job affiche:

- le nom du job;
- la coche `Actif` / `Desactive`;
- le dernier statut;
- le bouton `Voir dernier log`.

Le nom et le cron ne sont plus editables directement dans la liste. Pour modifier un job, cliquez sur sa carte.

### Ajouter Ou Modifier Un Job

Le bouton `+ Ajouter un job` ouvre une fenetre de creation.

Un clic sur un job existant ouvre la meme fenetre en mode edition.

Champs disponibles:

- nom du job, obligatoire;
- expression cron, obligatoire;
- coche `Actif`;
- source;
- cible;
- exclusions rsync, optionnelles.

Champs obligatoires selon le type de source/cible:

- `Local`: chemin local obligatoire;
- `SMB/CIFS`: adresse IP ou nom et partage reseau obligatoires;
- `SMB/CIFS`: login, mot de passe, sous-dossier et domaine/workgroup optionnels.

L'enregistrement est bloque si un champ obligatoire est vide. Les champs concernes sont alors marques en rouge dans la fenetre.

Actions disponibles dans la fenetre:

- `Enregistrer`: sauvegarde le job et regenere la planification cron;
- `Supprimer`: supprime le job apres confirmation;
- `Simuler`: enregistre le job puis lance un dry-run rsync;
- `Lancer`: enregistre le job puis lance l'execution reelle;
- `Tester montages`: enregistre le job puis teste les montages et l'ecriture destination.

Le bouton `Tester montages` apparait seulement si la source ou la cible utilise `SMB/CIFS`.

### Actif Et Desactive

La coche `Actif` controle la planification automatique.

- `Actif`: le job est ajoute au crontab genere.
- `Desactive`: le job reste configure, mais le cron l'ignore.

Les actions manuelles restent disponibles meme si le job est desactive. Cela permet de tester ou lancer ponctuellement un job sans le remettre dans la planification.

Pour creer un job utilisable uniquement en manuel, renseignez le cron normalement puis decochez `Actif`. Le job ne sera pas ajoute a la planification, mais restera disponible pour `Simuler`, `Lancer` et `Tester montages`.

### Actualiser

Le bouton `Actualiser` recharge les jobs et les statuts depuis l'addon. Il est utile si un job cron s'est execute pendant que l'interface etait ouverte.

## Sources Et Cibles

La source et la cible sont configurees separement. Chaque cote peut etre en mode `Local` ou `SMB/CIFS`.

### Mode Local

En mode `Local`, indiquez un chemin visible depuis le conteneur de l'addon.

Exemples:

```text
/share/photos
/media/camera
/backup/archives
```

Les chemins disponibles dependent des dossiers exposes par Home Assistant dans la configuration de l'addon.

### Mode SMB/CIFS

En mode `SMB/CIFS`, renseignez:

- `Adresse IP ou nom`: adresse IP, nom DNS ou nom NetBIOS du serveur;
- `Partage reseau`: nom du partage SMB, sans `//serveur/`;
- `Sous-dossier dans le partage`: chemin interne optionnel;
- `Login`: utilisateur SMB;
- `Mot de passe`: mot de passe SMB;
- `Domaine/Workgroup`: optionnel.

Exemple:

```text
Adresse IP ou nom:
192.168.1.20

Partage reseau:
Documents

Sous-dossier dans le partage:
Archives/2026
```

L'addon monte automatiquement:

```text
//192.168.1.20/Documents
```

Puis utilise le sous-dossier comme chemin rsync:

```text
/mnt/.../Archives/2026
```

## Options Integrees

Les options techniques rsync et CIFS ne sont plus exposees dans l'interface. L'addon applique un profil integre pour reduire les erreurs de configuration.

### Profil CIFS

Pour les montages SMB/CIFS, l'addon utilise:

```text
iocharset=utf8
vers=3.0
sec=ntlmssp
noperm
noserverino
nounix
```

Le fichier de credentials est cree temporairement pendant le montage puis supprime. Les options de montage apparaissent dans les logs avec le chemin du fichier credentials masque.

### Profil Rsync

Pour `Simuler` et `Lancer`, l'addon utilise:

```sh
rsync -a -v -h --delete
```

En simulation, il ajoute:

```sh
--dry-run
```

Si la cible est en `SMB/CIFS`, il ajoute aussi:

```sh
--inplace --no-perms --no-owner --no-group --chmod=ugo=rwX
```

Ces options evitent plusieurs soucis courants avec les destinations SMB/CIFS:

- fichiers temporaires rsync difficiles a creer sur certains partages;
- droits source non reutilisables tels quels cote destination;
- fichiers devenant non reinscriptibles au passage suivant.

Les options effectivement appliquees sont ecrites dans le dernier log du job:

```text
[RSYNC] Options appliquees: ...
```

Attention: `--delete` supprime dans la destination les fichiers absents de la source. Utilisez `Simuler` avant un premier lancement ou apres une modification importante.

## Exclusions Rsync

Chaque job peut definir des exclusions, une regle par ligne.

Exemples:

```text
cache/
*.tmp
@eaDir/
#recycle/
```

Les exclusions sont appliquees a `Simuler` et `Lancer` avec `--exclude-from`. Elles ne sont pas utilisees par `Tester montages`, car ce mode ne lance pas rsync.

Quand des exclusions sont presentes, le log indique le nombre de regles actives.

## Planification Cron

Chaque job utilise une expression cron a 5 champs:

```text
minute heure jour_du_mois mois jour_de_la_semaine
```

Exemples:

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

Le premier jour de chaque mois a 04:00.

Apres chaque ajout, modification, suppression ou import de jobs, l'addon:

1. ecrit `/data/jobs.json`;
2. normalise les jobs;
3. regenere `/var/spool/cron/crontabs/root`;
4. ignore les jobs desactives;
5. redemarre la planification via le service `crond`.

## Statuts Et Logs

Chaque execution met a jour:

- `/data/status.json`: dernier statut connu de chaque job;
- `/data/logs/<job_id>.log`: dernier log complet du job.

Statuts possibles dans l'interface:

- `Jamais execute`: aucun statut disponible;
- `Succes`: execution ou simulation terminee sans erreur;
- `Montages OK`: test de montage reussi;
- `Echec`: rsync a retourne une erreur;
- `Erreur montage`: montage, acces source ou ecriture destination impossible;
- `Desactive`: le cron ignore ce job.

Le statut peut aussi afficher:

- date et heure de derniere execution;
- declenchement `manuel` ou `cron`;
- mode `run`, `dry-run` ou `test montages`;
- duree;
- resume rsync: envoye, recu, total.

Le bouton `Voir dernier log` ouvre le dernier log persistant du job dans l'interface.

## Onglet SMTP

L'onglet `SMTP` configure l'envoi des rapports email.

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

Le bouton `Envoyer un Test` sauvegarde la configuration courante puis envoie un email de test.

Les emails automatiques sont envoyes apres les executions reelles (`Lancer` ou cron). Les simulations et les tests de montage n'envoient pas de rapport email.

### Exemple Gmail

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

Pour Gmail, utilisez un mot de passe d'application Google.

## Onglet GESTION

L'onglet `GESTION` permet d'importer et d'exporter les configurations depuis le navigateur.

Boutons disponibles:

- `Export config email`;
- `Export config jobs`;
- `Import config email`;
- `Import config jobs`.

Les exports contiennent les mots de passe SMTP et SMB/CIFS en clair. Conservez ces fichiers dans un emplacement sur.

Lors d'un import de jobs, l'addon normalise automatiquement:

- `id`: genere si absent, invalide ou duplique;
- `enabled`: `true` par defaut si absent;
- `excludes`: liste vide par defaut si absent.

Les anciens champs d'options rsync/CIFS qui ne sont plus utilises sont retires lors de la normalisation.

## Donnees Persistantes

Les fichiers persistants sont stockes dans `/data`:

```text
/data/jobs.json
/data/config.json
/data/status.json
/data/logs/<job_id>.log
```

Les jobs possedent un identifiant stable de type `job_...`. Cet identifiant sert a relier l'interface, le cron, les statuts et les logs, meme si l'ordre des jobs change.

## Permissions Et Chemins Locaux

Les chemins locaux utilisables par l'addon dependent des dossiers exposes par Home Assistant dans la configuration de l'addon.

Dans le conteneur, les chemins les plus courants sont:

```text
/share
/media
/backup
```

Pour SMB/CIFS, l'addon a besoin de privileges de montage reseau:

```yaml
privileged:
  - SYS_ADMIN
  - DAC_READ_SEARCH
```

Ces privileges sont declares dans la configuration de l'addon.

## Logs De L'Addon

Les logs utiles sont visibles dans le journal de l'addon Home Assistant et, pour chaque job, dans `Voir dernier log`.

Prefixes importants:

```text
[API]
[CRON]
[CIFS]
[RUNNER]
[RSYNC]
[EMAIL]
```

Exemple de lignes utiles:

```text
[CIFS] Options montage source: credentials=<masque>,iocharset=utf8,vers=3.0,noperm,sec=ntlmssp,noserverino,nounix
[RSYNC] Profil SMB/CIFS actif.
[RSYNC] Options appliquees: -a -v -h --delete --inplace --no-perms --no-owner --no-group --chmod=ugo=rwX
```

## Verifications Utiles

Depuis le conteneur de l'addon:

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

Regenerer manuellement le cron:

```sh
/usr/local/bin/rsync_cron.sh
```

Lancer un job manuellement depuis le conteneur:

```sh
/usr/local/bin/rsync_manager.sh mount_test job_xxx manual
/usr/local/bin/rsync_manager.sh dry job_xxx manual
/usr/local/bin/rsync_manager.sh run job_xxx manual
```

## Depannage

### Le Job Ne S'execute Pas Automatiquement

Verifiez:

- que le job est actif;
- que l'expression cron contient bien 5 champs;
- que `/var/spool/cron/crontabs/root` contient la ligne du job;
- que le journal contient des lignes `[CRON]`;
- que `crond` tourne.

### Le Job Est Desactive Mais Peut Encore Etre Lance

C'est normal. Le mode `Desactive` empeche uniquement l'execution automatique par cron. Les actions manuelles restent disponibles.

### Le Test Montages Echoue

Verifiez:

- l'adresse IP ou le nom du serveur;
- le nom du partage, sans `//serveur/`;
- le sous-dossier, separe du nom du partage;
- le login et le mot de passe;
- le domaine/workgroup si le serveur en demande un;
- les droits du compte SMB;
- les droits d'ecriture sur la destination;
- l'acces reseau depuis Home Assistant.

### Rsync Echoue Sur Une Destination SMB/CIFS

Regardez le dernier log du job. Il contient:

- les options de montage CIFS appliquees;
- les options rsync appliquees;
- la sortie complete de rsync.

L'addon applique deja un profil SMB/CIFS integre. Si l'erreur persiste, verifiez surtout les droits du compte SMB, le chemin destination et les permissions du partage cote serveur.

### Les Exclusions Ne S'appliquent Pas

Verifiez:

- une exclusion par ligne;
- pas de guillemets autour des motifs;
- un motif relatif au chemin vu par rsync;
- la ligne `[RSYNC] Exclusions actives` dans le log.

### Gmail Refuse L'envoi

Verifiez:

- `TLS actif = Oui`;
- `STARTTLS = Oui`;
- port `587`;
- mot de passe d'application Google;
- expediteur coherent avec le compte Gmail.
