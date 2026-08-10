# UniFi Log Explorer

Collectez et explorez localement les Traffic Flows et événements CEF/Syslog
d’un environnement UniFi.

## Mise en route

1. Configurez l’URL HTTPS locale, le site UniFi et une clé API.
2. Ajoutez dans `allowed_source_ips` chaque équipement autorisé à envoyer des
   événements.
3. Vérifiez les ports publiés, puis démarrez l’App.
4. Créez le compte administrateur local depuis l’interface web.
5. Testez l’API depuis **Paramètres**, puis activez la collecte des Traffic Flows
   dans les options Home Assistant.
6. Configurez UniFi Network pour envoyer Syslog/CEF vers le port UDP publié.

La clé API est chiffrée dans le volume privé puis retirée des options au
redémarrage. La page Paramètres affiche la configuration en lecture seule : les
modifications s’effectuent exclusivement dans les options de l’App.

## Interface

- **Vue d’ensemble** : état de collecte et principaux indicateurs sur 24 heures.
- **Traffic Flows** : recherche, filtres, pagination et détail complet.
- **CEF / Syslog** : recherche par contenu, type, source et période.
- **Paramètres** : thème, test API, export diagnostic et résumé de configuration.

L’App utilise une authentification locale et n’active pas Ingress. Gardez les
ports web et UDP sur un réseau de confiance. Consultez le
[guide français complet](README.fr.md) ou la
[documentation anglaise](README.md) pour la configuration, la sécurité, le
stockage et les limites connues.
