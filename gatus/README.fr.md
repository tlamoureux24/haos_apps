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
- secrets SMS, SMTP et Home Assistant facultatifs conservés dans les options privées de l'App ;
- aucun secret dans config.yaml ou dans le dépôt GitHub ;
- interface web locale sur le port 8080 ;
- watchdog Supervisor interne ;
- sauvegarde Home Assistant à froid ;
- profil AppArmor personnalisé ;
- aucun accès Home Assistant imposé : le fournisseur d'alertes Home Assistant de Gatus reste facultatif ;
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
- email_to ;
- homeassistant_token, uniquement si le fournisseur `homeassistant` de Gatus est activé.

Sans fournisseur d'alerte activé, l'App démarre sans aucune de ces valeurs.
Laissez notamment email_port vide tant que le fournisseur e-mail est désactivé.
Le champ homeassistant_token peut lui aussi rester vide tant que le fournisseur
Home Assistant n'est pas utilisé.

Au premier démarrage, l'App crée automatiquement :

    /addon_configs/<identifiant_du_dépôt>_gatus/config.yaml

Gatus refusant de démarrer sans endpoint ni suite, le fichier initial contient
uniquement un contrôle ICMP local sur `127.0.0.1`. Il ne contient aucune donnée
provenant de votre réseau. Remplacez ce contrôle par les vôtres depuis File
editor, Studio Code Server, Samba ou SSH selon les outils installés.

Les changements de config.yaml sont rechargés automatiquement par Gatus. Une
modification des options privées exige un redémarrage de l'App, car les
variables d'environnement sont injectées au démarrage.

## Secrets

Le fichier Gatus peut utiliser les variables suivantes :

    ${GATUS_SMS_USER}
    ${GATUS_SMS_PASSWORD}
    ${GATUS_EMAIL_FROM}
    ${GATUS_EMAIL_USERNAME}
    ${GATUS_EMAIL_PASSWORD}
    ${GATUS_EMAIL_HOST}
    ${GATUS_EMAIL_PORT}
    ${GATUS_EMAIL_TO}
    ${GATUS_HOMEASSISTANT_TOKEN}

Le lanceur les alimente depuis les options Supervisor. Elles ne sont jamais
écrites dans addon_config, intégrées à l'image ou enregistrées dans les logs.
Supervisor les conserve dans les données privées de l'App afin de les restaurer
après un redémarrage et de les inclure dans les sauvegardes.

## Alertes Home Assistant facultatives

Gatus fournit nativement un fournisseur `homeassistant`. Lorsqu'il est activé,
il publie dans Home Assistant un événement `gatus_alert` au déclenchement d'une
alerte et, avec `send-on-resolved: true`, à son rétablissement.

Pour l'utiliser :

1. créez dans Home Assistant un jeton d'accès adapté à cet usage ;
2. renseignez ce jeton dans l'option privée `homeassistant_token` de l'App ;
3. redémarrez l'App pour rendre `GATUS_HOMEASSISTANT_TOKEN` disponible ;
4. ajoutez explicitement le fournisseur `homeassistant` dans votre config.yaml Gatus ;
5. ajoutez `type: homeassistant` uniquement aux endpoints qui doivent publier ces événements.

Exemple :

    alerting:
      homeassistant:
        url: "http://ADRESSE_IP_HOME_ASSISTANT:8123"
        token: "${GATUS_HOMEASSISTANT_TOKEN}"
        default-alert:
          send-on-resolved: true
          failure-threshold: 2
          success-threshold: 2

Puis, sur un endpoint :

    alerts:
      - type: homeassistant

Cette fonction est entièrement facultative. Ajouter l'option privée dans l'App
n'active rien à elle seule et la configuration initiale conserve tous les
fournisseurs d'alerte désactivés.

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
- fournit des exemples commentés pour l'e-mail, l'API SMS Free Mobile et le fournisseur Home Assistant ;
- fournit uniquement un endpoint loopback local nécessaire au démarrage.

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
