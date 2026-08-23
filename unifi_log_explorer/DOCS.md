# UniFi Log Explorer

Collectez et explorez localement les Traffic Flows et événements CEF/Syslog
d’un environnement UniFi.

## Mise en route

1. Configurez l’URL HTTPS locale, le site UniFi, une clé API et soit la validation TLS système, soit l’empreinte SHA-256 du certificat autogénéré.
2. Ajoutez dans `allowed_source_ips` chaque équipement autorisé à envoyer des
   événements.
3. Conservez UDP `5514` publié, puis démarrez l’App.
4. Ouvrez l’interface Ingress en étant authentifié comme administrateur Home Assistant.
5. Testez l’API depuis **Paramètres**, puis activez la collecte des Traffic Flows
   dans les options Home Assistant.
6. Configurez UniFi Network pour envoyer Syslog/CEF vers le port UDP publié.

La clé API est chiffrée dans le volume privé puis retirée des options au
redémarrage. La page Paramètres affiche la configuration en lecture seule : les
modifications s’effectuent exclusivement dans les options de l’App.

Sans certificat reconnu ou empreinte SHA-256 correcte, l’App refuse la connexion
avant l’envoi de la clé API et inscrit la cause explicite dans ses logs. Relevez
l’empreinte avec `openssl s_client -connect HOTE:443 -servername HOTE </dev/null
2>/dev/null | openssl x509 -noout -fingerprint -sha256`.

## Interface

- **Vue d’ensemble** : état de collecte et principaux indicateurs sur 24 heures.
- **Traffic Flows** : recherche, filtres, pagination et détail complet.
- **CEF / Syslog** : recherche par contenu, type, source et période.
- **Paramètres** : thème, test API, export diagnostic et résumé de configuration.

L’interface est disponible en français et en anglais. La langue du navigateur
est utilisée au premier accès, puis le choix manuel est mémorisé localement.

Home Assistant assure l’authentification de l’interface Ingress. Le port Web
interne `8090` n’est pas exposé sur le LAN ; UDP `5514` reste publié pour les
messages Syslog/CEF. Consultez le
[guide français complet](README.fr.md) ou la
[documentation anglaise](README.md) pour la configuration, la sécurité, le
stockage et les limites connues.
