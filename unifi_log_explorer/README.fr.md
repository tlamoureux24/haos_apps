# UniFi Log Explorer

UniFi Log Explorer est une App Home Assistant autonome qui collecte et explore
les Traffic Flows ainsi que les exports Syslog/CEF d'une passerelle
UniFi. L'ensemble fonctionne localement sur le réseau domestique.

Elle fournit :

- un récepteur Syslog/CEF UDP ;
- un filtrage strict par adresse IP source avant analyse ou stockage ;
- une interface web autonome protégée par un compte administrateur local ;
- une vue d'ensemble des clients, services, destinations et actions ;
- un explorateur de flows filtrable, paginé, avec fiche détaillée ;
- une interface responsive en mode clair ou sombre ;
- un explorateur CEF / Syslog paginé avec recherche par contenu, type, source et période ;
- une rétention en durée et en nombre maximal d'enregistrements ;
- un export JSON du diagnostic, sans adresse IP de l'émetteur.
- un test non persistant de l'endpoint interne Traffic Flows avec une clé API dédiée.

Il n'y a volontairement pas d'Ingress. L'interface est publiée sur le réseau
local, comme AdGuard Home ou Nginx Proxy Manager.

## Installation et premier démarrage

1. Installez l'App et vérifiez `allowed_source_ips`. Par défaut, seule
   `192.168.1.1` est acceptée.
2. Démarrez l'App puis ouvrez son interface web.
3. Créez le compte administrateur local. Le mot de passe doit contenir au moins
   12 caractères et seul son dérivé `scrypt` salé est conservé.
4. Activez l'export SIEM/CEF vers la même adresse, port UDP `5514`.

## Test de l'API Traffic Flows

Configurez `unifi_base_url`, généralement `https://192.168.1.1`, conservez
`unifi_site_slug` à `default`, puis saisissez une clé API UniFi dédiée. Au
redémarrage, la clé est chiffrée dans le volume privé et le champ d'option est
automatiquement vidé. Ne ressaisissez pas la clé tant qu'elle ne change pas.

Ouvrez ensuite l'interface et utilisez **Tester l'API Traffic Flows**. Le test
interroge les cinq dernières minutes, demande au maximum un flow et ne conserve
aucune donnée retournée. Son seul objectif est de déterminer si l'endpoint
interne accepte l'authentification `X-API-Key`.

Laissez `verify_ssl` désactivé pour le certificat autosigné habituel de la
console. Activez-le uniquement si la chaîne du certificat est reconnue dans
l'App.

### Collecte des flows

Une fois le test réussi, activez `flow_collection_enabled`. Par défaut, l'App :

- importe les dernières 24 heures au premier démarrage ou lors d'une migration ;
- interroge l'UCG toutes les 120 secondes ;
- lit au maximum cinq pages récentes par cycle ;
- réconcilie les dernières 24 heures toutes les six heures pour les publications tardives ;
- pagine les réponses par lots de 100 ;
- découpe les fenêtres atteignant la limite UniFi de 10 000 résultats ;
- élimine les doublons grâce à l'identifiant stable du flow ;
- reste à deux requêtes par cycle lorsque l'UCG n'a publié aucun nouveau lot.

UniFi peut rendre les flows visibles par lots espacés de plusieurs heures. La
lecture depuis les éléments les plus récents évite de dépendre de cette latence
de publication et de la durée réelle des sessions.

Les flows sont conservés dans une table SQLite séparée et bornés par
`retention_hours` et `max_records`. Ils ne sont pas inclus dans l'export JSON
diagnostique.

Les ports hôtes peuvent être modifiés dans le panneau Réseau de l'App. Les ports
configurés côté UniFi doivent alors correspondre aux ports hôtes.

## Sécurité

Les datagrammes dont l'adresse source ne figure pas dans `allowed_source_ips`
ne sont ni analysés ni conservés. Seul leur nombre est incrémenté. Les adresses
doivent être des IPv4 ou IPv6 exactes ; les sous-réseaux CIDR ne sont pas admis.

Le port web `8090` doit rester accessible uniquement depuis le LAN ou un VPN.
Pour un accès HTTPS, placez-le derrière Nginx Proxy Manager. Ne publiez jamais
les ports `8090` ou `5514` directement sur Internet.

La base diagnostique est incluse dans les sauvegardes de cette première phase.
Elle est bornée par `retention_hours` et `max_records`. La future base analytique
volumineuse sera séparée et exclue des sauvegardes.

## Limites actuelles

- Transport UDP uniquement pour Syslog/CEF.
- Il ne s'agit pas encore d'un historique exhaustif ni d'un moteur d'alertes.
- L'endpoint Traffic Flows utilisé par UniFi n'est pas documenté publiquement
  et peut évoluer avec une mise à jour de UniFi Network.
