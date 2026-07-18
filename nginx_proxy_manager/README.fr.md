# Nginx Proxy Manager pour Home Assistant

Documentation : [Français](README.fr.md) | [English](README.md)

Cette App Home Assistant est volontairement une enveloppe très fine autour de
l'image Docker officielle
[Nginx Proxy Manager](https://github.com/NginxProxyManager/nginx-proxy-manager).
Elle ne crée aucun fork, ne modifie, n'ajoute et ne retire aucune fonctionnalité
de NPM.

Elle ajoute uniquement les éléments nécessaires au Supervisor :

- les métadonnées Home Assistant et les ports standards 80, 81 et 443 ;
- la persistance des données NPM dans `/data` ;
- la persistance de Let's Encrypt dans `/data/letsencrypt` ;
- une sauvegarde à froid pour garantir la cohérence de SQLite ;
- le suivi automatisé des versions stables officielles de NPM.

La version de l'App suit le format `<version NPM>-<révision du paquet>`. Par
exemple, `2.15.1-1` contient NPM officiel `2.15.1`, révision d'emballage `1`.

## Installation

Ajoutez ce dépôt d'Apps Home Assistant :

```text
https://github.com/tlamoureux24/haos_apps
```

Installez ensuite **Nginx Proxy Manager** depuis la boutique. La première
construction télécharge l'image officielle NPM épinglée et ne crée qu'une
minuscule couche d'adaptation Home Assistant.

L'App prend en charge `amd64` et `aarch64`, comme les images NPM actuelles.

## Réseau

| Port du conteneur | Port hôte par défaut | Usage |
| --- | ---: | --- |
| `80/tcp` | `80` | HTTP public et challenge Let's Encrypt HTTP-01 |
| `81/tcp` | `81` | Interface d'administration NPM |
| `443/tcp` | `443` | HTTPS public |

Home Assistant publie les ports configurés sur l'hôte. L'App ne peut pas lier
elle-même le port 81 à une interface LAN particulière. La restriction LAN/VPN
doit donc être appliquée par le routeur et le pare-feu :

- ne rediriger depuis Internet que les ports 80 et 443 ;
- ne jamais rediriger le port 81 depuis Internet ;
- limiter le port 81 aux réseaux LAN/VPN de confiance ;
- conserver la double authentification du compte administrateur NPM.

Cette App n'utilise volontairement pas l'Ingress Home Assistant : le frontend
officiel NPM n'est pas conçu pour fonctionner sous un préfixe d'URL Ingress.

## Données persistantes et sauvegardes

NPM utilise normalement deux volumes Docker : `/data` et `/etc/letsencrypt`.
Home Assistant persiste déjà `/data`. L'enveloppe relie donc
`/etc/letsencrypt` à `/data/letsencrypt`. La base SQLite, la configuration des
proxys, les certificats, les clés privées, les renouvellements et les identifiants
DNS sont ainsi inclus dans les sauvegardes Home Assistant.

L'App demande une **sauvegarde à froid** : le Supervisor l'arrête brièvement
pendant la copie puis la redémarre. Cela garantit la cohérence de SQLite.

Les sauvegardes Home Assistant sont sensibles : elles contiennent les secrets
NPM et les clés privées des certificats.

## Première configuration NPM

Ouvrez `http://IP_HOME_ASSISTANT:81`. Depuis NPM `2.13.0`, un assistant de
première configuration remplace l'ancien compte partagé par défaut. Créez le
compte administrateur puis activez sa double authentification.

Pour un nom d'hôte inconnu, le site par défaut recommandé est
**No Response (444)**.

## Publier Home Assistant

Créez un Proxy Host avec :

- schéma : `http` ;
- nom d'hôte de destination : `homeassistant` ;
- port de destination : `8123`, sauf configuration HA personnalisée ;
- prise en charge WebSocket activée ;
- le certificat SSL voulu et **Force SSL** activé.

Home Assistant doit faire confiance au reverse proxy immédiat. Configurez
`use_x_forwarded_for` et la valeur `trusted_proxies` la plus restrictive correcte
dans `configuration.yaml`. L'exemple officiel Home Assistant utilise le réseau
d'Apps `172.30.33.0/24`, mais l'adresse exacte de l'App NPM est préférable si
elle reste stable dans votre installation.

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 172.30.33.0/24
```

N'ajoutez pas de plage LAN complète si elle ne contient pas réellement des
reverse proxys de confiance.

## Certificats

Avec une IP publique fixe, un nom d'hôte classique et sans certificat wildcard,
HTTP-01 est le choix le plus simple et évite de stocker un token API DNS. Le port
public 80 doit rester redirigé vers NPM pour l'émission et les renouvellements.

Utilisez DNS-01 pour un certificat wildcard, si le port 80 ne peut pas être
exposé ou pour une émission destinée à des noms internes. Les identifiants DNS
enregistrés par NPM sont persistés et inclus dans les sauvegardes Home Assistant.

## Migrer une installation NPM existante

Ne démarrez jamais simultanément l'ancien conteneur NPM et cette App s'ils
utilisent les mêmes ports hôte.

Avant la migration, sauvegardez intégralement les anciens volumes `data` et
`letsencrypt`. L'App n'importe pas automatiquement les volumes Docker externes.
Pour une petite installation, recréer les Proxy Hosts est généralement plus sûr
et plus simple. Conservez l'ancien conteneur arrêté mais intact jusqu'à validation
du nouveau proxy et des renouvellements de certificats.

## Mises à jour automatiques

Le dépôt interroge chaque jour la dernière version officielle GitHub et permet
aussi un déclenchement manuel depuis GitHub Actions. Lorsqu'une nouvelle version
stable au format sémantique existe, le workflow :

1. vérifie que l'image Docker officielle existe pour `amd64` et `arm64` ;
2. actualise la version épinglée et remet la révision du paquet à `1` ;
3. valide les versions, les métadonnées, les scripts et les visuels officiels ;
4. construit l'enveloppe puis démarre NPM pour un test HTTP ;
5. commit directement la mise à jour validée dans le dépôt.

Home Assistant affiche ensuite la nouvelle version de l'App comme mise à jour
disponible. Son installation reste une action volontaire dans Home Assistant.

Le dépôt doit autoriser GitHub Actions à écrire son contenu dans
**Settings > Actions > General > Workflow permissions**. Aucun secret externe ni
token d'accès personnel n'est nécessaire : le workflow utilise le token
temporaire fourni par GitHub.

## Périmètre et support

Les fonctionnalités, les proxys, les certificats et les correctifs de sécurité
sont fournis par l'image officielle NPM. Ce dépôt maintient uniquement
l'emballage Home Assistant et son automatisation de mise à jour.

- NPM officiel : <https://github.com/NginxProxyManager/nginx-proxy-manager>
- Enveloppe Home Assistant : <https://github.com/tlamoureux24/haos_apps/tree/main/nginx_proxy_manager>

L'icône et le logo officiels NPM sont repris sans modification. Les sources et
sommes de contrôle figurent dans [UPSTREAM_ASSETS.md](UPSTREAM_ASSETS.md).
