# AdGuard Home pour Home Assistant

Documentation : [Français](README.fr.md) | [English](README.md)

Cette App Home Assistant est volontairement une enveloppe très fine autour de
l'image Docker officielle
[AdGuard Home](https://github.com/AdguardTeam/AdGuardHome). Elle ne crée aucun
fork et ne modifie pas AdGuard Home. Home Assistant OS sert uniquement d'hôte
au conteneur : AdGuard Home conserve son propre compte administrateur et ne
reçoit aucun accès aux API Home Assistant ou Supervisor.

L'App ajoute seulement :

- les métadonnées Home Assistant et des ports réseau configurables ;
- la persistance de la configuration et du répertoire de travail officiels dans `addon_config` ;
- un lanceur non privilégié et un profil AppArmor ;
- des sauvegardes Home Assistant à froid ;
- le suivi et la validation automatisés des versions stables officielles.

Il n'y a volontairement ni Ingress, ni délégation d'authentification, ni
découverte Home Assistant, ni `host_network`, ni mode privilégié, ni token
Supervisor.

La version suit `<version AdGuard Home>-<révision du paquet>`. Par exemple,
`0.107.78-6` contient AdGuard Home officiel `0.107.78`, révision `6`.

## Installation

Ajoutez ce dépôt d'Apps Home Assistant :

```text
https://github.com/tlamoureux24/haos_apps
```

Installez **AdGuard Home**, démarrez l'App puis ouvrez
`http://IP_LAN_HOME_ASSISTANT:3000`. Dans l'assistant officiel, choisissez :

> [!WARNING]
> **PORT D'ADMINISTRATION OBLIGATOIRE : remplacez le port web `80` proposé par
> défaut par `3000`.** Si vous conservez `80`, le dernier bouton de l'assistant
> tentera d'ouvrir `http://IP_LAN_HOME_ASSISTANT:80`, qui n'est pas publié par
> défaut et peut déjà être utilisé par un autre service. Cette valeur doit être
> modifiée directement dans l'assistant initial.

- interface web : toutes les interfaces, port `3000` ;
- serveur DNS : toutes les interfaces, port `53` ;
- un identifiant administrateur unique et un mot de passe fort.

Le lanceur remplace également `80` par `3000` avant le redémarrage final comme
garde-fou, mais il ne peut pas corriger le lien déjà généré par le dernier
bouton de l'assistant. Le port 80 reste ainsi disponible séparément pour HTTP
ou DoH et peut rester désactivé.

AdGuard Home exige des privilèges administrateur pendant la création de son
tout premier fichier de configuration. Le lanceur détecte la fin de l'assistant,
redémarre brièvement AdGuard Home puis continue immédiatement avec l'utilisateur
non privilégié `nobody`. La page peut se déconnecter quelques secondes à la fin
de l'assistant.

Ne publiez jamais le port d'administration sur Internet. Limitez-le aux clients
LAN et VPN de confiance avec le routeur ou le pare-feu.

L'App prend en charge `amd64` et `aarch64`.

## Isolation et adresses clientes

L'App utilise le réseau bridge Docker. Les ports DNS sont publiés par le
Supervisor et `host_network` est volontairement absent. AdGuard Home conserve
ainsi son propre espace réseau et n'accède pas directement à toutes les
interfaces réseau de l'hôte HAOS.

La publication des ports Docker sous Linux conserve normalement l'adresse
source des clients DNS. Vérifiez-le après installation dans **Tableau de bord →
Meilleurs clients** ou dans le journal des requêtes. Si toutes les requêtes
apparaissent exceptionnellement sous une seule adresse de passerelle Docker,
documentez l'environnement avant de modifier le modèle de sécurité.

Les clients doivent interroger directement l'adresse LAN de Home Assistant. Si
le routeur reçoit leurs requêtes puis les relaie vers AdGuard Home, AdGuard Home
verra le routeur comme client.

## Ports réseau

Seuls le DNS classique et l'interface d'installation sont activés par défaut.
Tous les autres ports de service officiels sont disponibles dans la
configuration Réseau de l'App et restent désactivés tant qu'aucun port hôte ne
leur est attribué.

| Port du conteneur | Défaut | Usage |
| --- | ---: | --- |
| `53/tcp` | `53` | DNS classique sur TCP |
| `53/udp` | `53` | DNS classique sur UDP |
| `3000/tcp` | `3000` | Installation initiale et administration |
| `80/tcp` | désactivé | HTTP et DNS-over-HTTPS optionnel |
| `443/tcp` | désactivé | HTTPS et DNS-over-HTTPS |
| `443/udp` | désactivé | HTTPS/DoH sur HTTP/3 |
| `3000/udp` | désactivé | HTTPS alternatif sur HTTP/3 |
| `853/tcp` | désactivé | DNS-over-TLS |
| `853/udp` | désactivé | DNS-over-QUIC |
| `784/udp` | désactivé | DNS-over-QUIC alternatif |
| `8853/udp` | désactivé | DNS-over-QUIC alternatif |
| `5443/tcp` | désactivé | DNSCrypt sur TCP |
| `5443/udp` | désactivé | DNSCrypt sur UDP |
| `6060/tcp` | désactivé | Interface de profilage Go pprof |

La valeur côté hôte de chaque port peut être modifiée dans le panneau Réseau de
Home Assistant. Changer un port hôte ne change pas le port d'écoute interne
d'AdGuard Home. Les services activés dans AdGuard Home et les ports du
conteneur doivent correspondre.

N'exposez jamais `3000` ou `6060` publiquement. N'activez les ports DNS chiffrés
entrants qu'après configuration volontaire d'un certificat valide et des règles
pare-feu adaptées.

## Pourquoi DHCP est absent

L'image officielle expose les ports DHCP 67 et 68, mais le serveur DHCP
d'AdGuard Home dépend des broadcasts de niveau 2 et exige le réseau hôte
Docker. Cette App refuse volontairement `host_network` : publier ces ports en
bridge laisserait croire à tort que DHCP peut fonctionner correctement.

Conservez le DHCP sur le routeur. Si le DHCP AdGuard Home est indispensable,
utilisez une installation séparée conçue pour `host_network` ; n'ajoutez pas
simplement les ports 67/68 à cette App.

## Administration en HTTPS

L'assistant initial est nécessairement accessible en HTTP sur le port 3000.
AdGuard Home peut ensuite fournir nativement son interface en HTTPS après
configuration d'un certificat et de sa clé privée dans
**Paramètres → Paramètres de chiffrement**.

Pour conserver l'administration HTTPS sur le port hôte 3000, configurez le
listener HTTPS d'AdGuard Home sur le port interne 3000 et déplacez ou désactivez
le listener HTTP qui entrerait en conflit. N'activez `3000/udp` que si HTTP/3
est souhaité. Activez ensuite l'option de l'App **Raccourci web HTTPS** afin que
le bouton **Ouvrir l'interface utilisateur web** utilise `https://`.

Cette option ne modifie que le schéma du raccourci. Elle n'active pas TLS,
n'installe aucun certificat, ne change aucun port AdGuard Home et ne redirige
pas HTTP. Ne l'activez qu'après avoir validé directement HTTPS dans un
navigateur. Un certificat associé à un nom d'hôte reconnu par les clients est
préférable à un certificat autosigné non approuvé.

Documentation officielle du DNS chiffré :
<https://github.com/AdguardTeam/AdGuardHome/wiki/Encryption>

## Données persistantes et sauvegardes

Les chemins officiels sont redirigés par les arguments de démarrage vers :

```text
/config/conf/AdGuardHome.yaml
/config/work/
```

Home Assistant associe `/config` au dossier `addon_config` privé de l'App. La
configuration, le hash du mot de passe administrateur, les filtres, statistiques
et journaux de requêtes sont donc persistants et inclus dans les sauvegardes.

L'App demande une sauvegarde à froid : le Supervisor l'arrête brièvement,
copie ses fichiers puis la redémarre. Les sauvegardes sont sensibles car elles
contiennent la configuration et le hash du mot de passe AdGuard Home.

## Déploiement DNS

Pour un filtrage cohérent, distribuez uniquement l'adresse LAN de Home Assistant
comme DNS aux clients via le DHCP du routeur. Ajouter le routeur ou un DNS
public non filtré en secondaire autorise un contournement : les clients ne
réservent pas forcément le second DNS aux seules pannes.

Une politique pare-feu optionnelle peut :

1. autoriser les clients vers `IP_HOME_ASSISTANT` en TCP/UDP 53 ;
2. bloquer leur DNS vers le routeur et Internet en TCP/UDP 53 ;
3. bloquer DoT et DoQ clients en TCP/UDP 853 ;
4. autoriser l'hôte Home Assistant vers les résolveurs amont choisis.

Le DNS-over-HTTPS utilise le port 443 ordinaire et ne peut pas être bloqué
globalement sans affecter le Web HTTPS. Les règles IPv4 et IPv6 doivent être
traitées séparément.

Configurez pour l'hôte HAOS lui-même un DNS externe statique. HAOS ne doit pas
dépendre exclusivement de l'App qu'il doit pouvoir démarrer, mettre à jour ou
réparer.

## DNS amont

AdGuard Home peut interroger des résolveurs amont en DNS classique, DoT, DoH,
DoQ ou DNSCrypt. Cette configuration se réalise dans l'interface officielle.
Le DNS amont chiffré ne nécessite pas d'exposer les ports entrants correspondants :
les connexions sortantes sont indépendantes des ports Réseau de l'App.

Documentation officielle :

- Base de connaissances actuelle : <https://adguard-dns.io/kb/adguard-home/overview/>
- Installation sécurisée : <https://adguard-dns.io/kb/adguard-home/running-securely/>
- Présentation : <https://github.com/AdguardTeam/AdGuardHome>
- Démarrage : <https://github.com/AdguardTeam/AdGuardHome/wiki/Getting-Started>
- Configuration : <https://github.com/AdguardTeam/AdGuardHome/wiki/Configuration>
- Docker : <https://github.com/AdguardTeam/AdGuardHome/wiki/Docker>
- Chiffrement : <https://github.com/AdguardTeam/AdGuardHome/wiki/Encryption>

## Modèle de sécurité

AdGuard Home s'exécute avec l'utilisateur amont `nobody` pendant son
fonctionnement normal. Le projet amont exige temporairement les droits
administrateur pour le premier assistant. Le lanceur détecte la création de
`AdGuardHome.yaml`, redémarre automatiquement le service, corrige les
propriétaires persistants puis abandonne immédiatement ses droits au profit de
`nobody:nogroup`. Le binaire officiel porte la capacité nécessaire à l'ouverture
des ports privilégiés après cette transition.

L'App n'accède ni à la configuration HA, ni aux sauvegardes générales, ni aux
périphériques, ni au socket Docker, ni aux API Supervisor. Son authentification
administrateur reste indépendante de Home Assistant.

L'hébergement sur HAOS signifie toujours qu'un administrateur Supervisor
compromis peut arrêter, reconfigurer, mettre à jour ou supprimer le conteneur.
L'App évite le partage automatique des identités et les privilèges API inutiles ;
elle ne peut pas créer une isolation absolue vis-à-vis de l'administrateur hôte.

## Mises à jour automatiques

Le dépôt vérifie chaque jour la dernière release stable officielle et accepte
aussi un lancement manuel depuis GitHub Actions. Lorsqu'une nouvelle version
sémantique apparaît, le workflow :

1. vérifie l'image Docker officielle pour `amd64` et `arm64` ;
2. actualise les versions amont et App ;
3. valide métadonnées, ports, invariants de sécurité, scripts et visuels ;
4. construit l'enveloppe et teste l'interface, l'installation et le DNS ;
5. commit directement la mise à jour validée dans le dépôt.

Home Assistant propose ensuite la nouvelle version. Son installation reste
volontaire. La mise à jour interne d'AdGuard Home est désactivée, comme dans
l'image Docker officielle.

Le workflow demande seulement `contents: write`. Aucun token personnel n'est
nécessaire si les permissions du dépôt autorisent GitHub Actions à écrire.

## Périmètre et support

Les fonctionnalités et correctifs de sécurité proviennent de l'image officielle.
Ce dépôt maintient uniquement l'emballage Home Assistant et son automatisation.

- Projet officiel : <https://github.com/AdguardTeam/AdGuardHome>
- Base de connaissances : <https://adguard-dns.io/kb/adguard-home/overview/>
- App Home Assistant : <https://github.com/tlamoureux24/haos_apps/tree/main/adguard_home>

Les visuels officiels sont repris sans modification ; leurs sources et sommes
de contrôle figurent dans [UPSTREAM_ASSETS.md](UPSTREAM_ASSETS.md).
