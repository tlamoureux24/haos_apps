# Gatus pour Home Assistant

[English documentation](README.md)

Cette App exécute le binaire officiel Gatus dans Home Assistant OS ou une
installation supervisée. Elle ne modifie pas Gatus et ajoute uniquement
l'intégration nécessaire au Supervisor.

La version de l'App suit le format version Gatus-révision. La première version
est basée sur Gatus 5.36.0.

## Principes

- binaire officiel extrait de l'image ghcr.io/twin/gatus ;
- configuration Gatus éditable dans le dossier addon_config dédié ;
- secrets SMS et SMTP conservés dans les options privées de l'App ;
- aucun secret dans config.yaml ou dans le dépôt GitHub ;
- interface web locale sur le port 8080 ;
- watchdog Supervisor interne ;
- sauvegarde Home Assistant à froid ;
- profil AppArmor personnalisé ;
- aucun accès à l'API Home Assistant ou Supervisor ;
- aucun mode privilégié, réseau hôte ou capacité NET_RAW.

Depuis Gatus 5.31.0, les contrôles ICMP fonctionnent avec les pings non
privilégiés lorsque Gatus ne tourne pas en root. Le lanceur lit les options,
puis exécute le binaire officiel sous l'utilisateur gatus.

## Installation

Ajoutez le dépôt suivant à la boutique des Apps Home Assistant :

    https://github.com/tlamoureux24/haos_apps

Installez ensuite Gatus.

## Premier démarrage

Toutes les options d'alerte sont facultatives. Renseignez uniquement celles du
ou des fournisseurs que vous activez dans config.yaml :

- sms_user ;
- sms_password ;
- email_from ;
- email_username ;
- email_password ;
- email_host ;
- email_port ;
- email_to.

Sans fournisseur d'alerte activé, l'App démarre sans aucune de ces valeurs.

Au premier démarrage, l'App crée automatiquement :

    /addon_configs/<identifiant_du_dépôt>_gatus/config.yaml

Le fichier initial est un squelette valide avec `endpoints: []` et ne contient
aucune adresse ni aucun nom provenant de votre réseau. Ajoutez vos contrôles
depuis File editor, Studio Code Server, Samba ou SSH selon les outils installés.

Les changements de config.yaml sont rechargés automatiquement par Gatus. Une
modification des options privées exige un redémarrage de l'App, car les
variables d'environnement sont injectées au démarrage.

## Secrets

Le fichier Gatus utilise uniquement ces variables :

    ${GATUS_SMS_USER}
    ${GATUS_SMS_PASSWORD}
    ${GATUS_EMAIL_FROM}
    ${GATUS_EMAIL_USERNAME}
    ${GATUS_EMAIL_PASSWORD}
    ${GATUS_EMAIL_HOST}
    ${GATUS_EMAIL_PORT}
    ${GATUS_EMAIL_TO}

Le lanceur les alimente depuis les options Supervisor. Elles ne sont jamais
écrites dans addon_config, intégrées à l'image ou enregistrées dans les logs.
Supervisor les conserve dans les données privées de l'App afin de les restaurer
après un redémarrage et de les inclure dans les sauvegardes.

## Accès

L'interface est disponible sur le réseau local :

    http://ADRESSE_IP_HOME_ASSISTANT:8080

L'App ne déclare volontairement ni Ingress ni raccourci Web UI. Gatus ne prend
pas en charge une publication fiable sous un sous-chemin et un raccourci
Supervisor pourrait reprendre le nom d'hôte externe de Home Assistant.

Le port 8080 doit rester limité au LAN ou au VPN, sauf décision explicite de le
publier derrière un reverse proxy correctement protégé.

## Configuration initiale

La configuration fournie :

- remplace l'option obsolète disable-monitoring-lock par concurrency: 0 ;
- laisse tous les fournisseurs d'alerte désactivés ;
- fournit des exemples commentés pour l'e-mail et l'API SMS Free Mobile ;
- ne fournit aucun endpoint réseau par défaut.

Le modèle n'est copié que si config.yaml n'existe pas. Une mise à jour de l'App
n'écrase donc jamais votre configuration.

## Historique persistant facultatif

L'installation d'origine utilise le stockage en mémoire. Pour conserver
l'historique après les redémarrages, décommentez dans config.yaml :

    storage:
      type: sqlite
      path: /data/gatus/gatus.db

Le dossier /data/gatus appartient à l'utilisateur non privilégié Gatus et est
inclus dans les sauvegardes de l'App.

## Limite de disponibilité

Cette App surveille correctement les équipements tant que l'hôte Home Assistant
fonctionne. Elle ne peut pas envoyer d'alerte si la machine Home Assistant
elle-même est complètement arrêtée. Prévoyez une surveillance externe si cette
couverture est nécessaire.

## Mises à jour

Un workflow quotidien détecte les nouvelles versions stables publiées par
TwiN/gatus, vérifie les images amd64 et arm64, met à jour les métadonnées,
construit l'App et exécute un test réel de démarrage et d'ICMP.

Le workflow commit la nouvelle version dans le dépôt. Home Assistant propose
ensuite la mise à jour, mais ne l'installe pas automatiquement sauf si
l'utilisateur active lui-même les mises à jour automatiques.

## Projet amont

- Gatus : https://github.com/TwiN/gatus
- Licence Gatus : Apache-2.0
