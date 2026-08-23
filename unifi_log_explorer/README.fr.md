# UniFi Log Explorer

UniFi Log Explorer est une App Home Assistant autonome pour collecter, conserver
et explorer localement l’activité d’un environnement UniFi. Elle réunit les
Traffic Flows fournis par l’API locale UniFi Network et les événements reçus en
Syslog/CEF.

L’interface d’administration est disponible exclusivement via Home Assistant
Ingress. Home Assistant authentifie l’utilisateur ; l’App ne possède plus de
compte ni mot de passe local et son port TCP interne `8090` n’est pas publié sur
le LAN.

## Fonctionnalités

- collecte périodique des Traffic Flows depuis une console UniFi locale ;
- réception Syslog/CEF en UDP avec liste stricte d’adresses sources autorisées ;
- déduplication et rattrapage périodique des flows publiés tardivement ;
- vue d’ensemble sur 24 heures avec principaux clients, services, destinations
  et actions ;
- explorateur de Traffic Flows avec recherche, filtres, périodes et pagination ;
- détail complet de chaque flow archivé ;
- explorateur CEF / Syslog avec recherche par contenu, type, source et période ;
- thèmes clair et sombre mémorisés dans le navigateur ;
- interface française ou anglaise détectée automatiquement, avec choix manuel
  mémorisé dans le navigateur ;
- page Paramètres regroupant test API, export diagnostic et résumé en lecture
  seule de la configuration Home Assistant ;
- accès Ingress authentifié par Home Assistant et supervision de la collecte ;
- exports CSV des résultats filtrés, graphique horaire sur 24 heures et outils
  de purge avec confirmation explicite ;
- rétention configurable par durée et par nombre maximal d’enregistrements.

## Prérequis

- Home Assistant OS ou Home Assistant Supervised ;
- une console UniFi Network accessible en HTTPS depuis l’App ;
- une clé API UniFi pour la collecte des Traffic Flows ;
- un port UDP accessible depuis les équipements UniFi pour Syslog/CEF ;
- un utilisateur administrateur authentifié dans Home Assistant.

## Installation

1. Ajouter ce dépôt à la boutique d’Apps Home Assistant.
2. Installer **UniFi Log Explorer**.
3. Renseigner les options adaptées au réseau avant de démarrer l’App.
4. Conserver le port UDP `5514` publié pour la réception Syslog/CEF.
5. Démarrer l’App et ouvrir son interface Ingress depuis Home Assistant.

## Configuration

| Option | Rôle |
| --- | --- |
| `allowed_source_ips` | Adresses IPv4 ou IPv6 exactes autorisées à envoyer des datagrammes Syslog/CEF. Les CIDR ne sont pas acceptés. |
| `retention_hours` | Durée de conservation des événements et des Traffic Flows. |
| `max_records` | Limite maximale appliquée séparément lors de l’entretien du stockage. |
| `unifi_base_url` | URL HTTPS locale de la console ou passerelle UniFi. |
| `unifi_site_slug` | Identifiant interne du site UniFi, souvent `default`. |
| `unifi_api_key` | Clé API utilisée pour lire les Traffic Flows. |
| `verify_ssl` | Vérifie la chaîne TLS de la console lorsqu’elle est activée. |
| `unifi_certificate_sha256` | Empreinte SHA-256 obligatoire lorsque `verify_ssl` est désactivé. |
| `flow_collection_enabled` | Active la collecte périodique des Traffic Flows. |
| `flow_poll_interval_seconds` | Intervalle entre deux collectes rapides. |
| `flow_initial_backfill_minutes` | Profondeur demandée pour l’import initial. |
| `log_level` | Niveau des journaux techniques de l’App. |

La configuration affichée dans la page **Paramètres** de l’interface est en
lecture seule. Toute modification doit être effectuée dans les options de l’App
Home Assistant, puis appliquée par un redémarrage.
Pour assurer la mise à jour des installations existantes, une ancienne valeur
`session_timeout_minutes` reste acceptée mais est ignorée : Home Assistant gère
désormais la session authentifiée.

## Configuration de Syslog/CEF dans UniFi

Dans UniFi Network, activer l’envoi des journaux vers un serveur SIEM :

- utiliser l’adresse de la machine Home Assistant ;
- utiliser le port UDP publié pour le récepteur Syslog/CEF ;
- sélectionner les catégories d’événements utiles ;
- ajouter à `allowed_source_ips` chaque équipement qui envoie directement ses
  propres messages.

Les datagrammes provenant d’une autre adresse sont refusés avant analyse et ne
sont pas conservés. Seul leur nombre est comptabilisé.

## Configuration de l’API Traffic Flows

Renseigner l’URL HTTPS locale, l’identifiant de site et une clé API UniFi, puis
activer `flow_collection_enabled`. Après le redémarrage :

1. la clé est chiffrée dans le volume privé de l’App ;
2. sa valeur est retirée des options Home Assistant ;
3. le bouton **Tester la connexion** de la page Paramètres permet de vérifier
   l’accès sans conserver le flow lu pendant le test.

UniFi ne propose pas nécessairement de permissions fines pour les clés API. Une
clé utilisée en lecture par cette App peut donc disposer de droits plus larges
que nécessaire. L’interface ne l’affiche jamais et son fichier de chiffrement
est exclu des sauvegardes. Après une restauration sur une autre installation,
la clé doit être renseignée à nouveau.

La validation TLS est obligatoire avant l’envoi de la clé API. Utilisez
`verify_ssl: true` lorsque la chaîne du certificat est reconnue. Pour un
certificat UniFi autogénéré, laissez cette option désactivée et renseignez
`unifi_certificate_sha256` ; une empreinte absente ou différente refuse la
connexion avant authentification. Pour la relever localement :

```sh
openssl s_client -connect 192.168.1.1:443 -servername 192.168.1.1 </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha256
```

## Fonctionnement de la collecte

Au premier démarrage avec la collecte activée, l’App importe une période
initiale, puis :

- interroge régulièrement les pages les plus récentes ;
- limite chaque collecte rapide à cinq pages ;
- déduplique les données avec l’identifiant stable fourni par UniFi ;
- réconcilie les dernières 24 heures toutes les six heures afin de récupérer les
  publications tardives ;
- découpe les fenêtres volumineuses pour rester sous la limite de résultats de
  l’API UniFi.

L’endpoint Traffic Flows utilisé par l’interface UniFi Network n’est pas une API
publique documentée. Une évolution de UniFi Network peut donc nécessiter une
adaptation de l’App.

## Interface web

- **Vue d’ensemble** : état de la collecte, volumes sur 24 heures et principaux
  clients, services, destinations et actions. Les blocs ouvrent les vues
  filtrées correspondantes.
- **Traffic Flows** : recherche par texte, source, destination, service,
  direction et période, avec pagination et fiche détaillée.
- **CEF / Syslog** : recherche dans tous les événements conservés, avec filtres
  par type, source et période, et accès aux données complètes de chaque événement.
- **Paramètres** : thème, test API, export diagnostic et configuration en lecture
  seule, état du stockage et maintenance des données.

## Stockage et sauvegardes

Les événements et Traffic Flows sont stockés dans SQLite dans le volume privé
de l’App. L’entretien périodique applique `retention_hours` et `max_records`.

La base est incluse dans les sauvegardes à froid Home Assistant. La clé servant
à chiffrer la clé API UniFi est volontairement exclue. L’export diagnostic ne
contient ni Traffic Flows complets, ni clé API, ni adresse IP de l’émetteur dans
la section des événements récents.

## Sécurité réseau

- accéder à l’administration uniquement via Home Assistant Ingress ;
- limiter le port UDP `5514` aux réseaux devant envoyer Syslog/CEF ;
- limiter autant que possible l’accès réseau de l’App à la console UniFi ;
- renouveler la clé API en cas de doute sur sa confidentialité.
- modifier l’empreinte SHA-256 uniquement après avoir vérifié indépendamment un renouvellement volontaire du certificat UniFi.

## Limites connues

- l’administration nécessite un administrateur authentifié dans Home Assistant ;
- Syslog/CEF utilise UDP et ne garantit donc pas la livraison de chaque message ;
- les clés API UniFi peuvent disposer de permissions plus larges que la lecture
  nécessaire ;
- l’endpoint Traffic Flows interne peut évoluer sans préavis ;
- l’App est un outil d’exploration locale, pas un SIEM complet ni un moteur
  d’alertes.
