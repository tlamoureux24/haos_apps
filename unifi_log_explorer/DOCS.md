# UniFi Log Explorer

Consultez le [guide français](README.fr.md) ou le [résumé anglais](README.md).

Au premier démarrage, ouvrez l'interface web et créez le compte administrateur.
Configurez ensuite l'UCG pour envoyer SIEM/CEF en UDP `5514` vers l'adresse de
Home Assistant. Par défaut, le collecteur n'accepte que les sources indiquées
dans `allowed_source_ips`.

Pour tester l'API Traffic Flows, renseignez l'URL HTTPS locale de l'UCG, le site
`default` et une clé API dédiée dans les options, puis redémarrez l'App. La clé
est chiffrée et le champ est automatiquement vidé. Lancez ensuite le test depuis
l'interface web ; un flow au maximum est lu et aucune donnée n'est conservée.

Après un test réussi, activez `flow_collection_enabled` pour archiver les flows
toutes les deux minutes. La collecte utilise pagination, déduplication et
une lecture rapide bornée à cinq pages. Une réparation initiale puis une
réconciliation toutes les six heures des dernières 24 heures récupèrent les lots publiés en retard.
Les données restent bornées par la durée de rétention et la limite
d'enregistrements configurées.

L'interface propose une vue d'ensemble, un explorateur filtrable des Traffic
Flows, leur détail complet et un explorateur séparé CEF / Syslog avec recherche,
filtres et pagination. Le thème clair
est utilisé par défaut et peut être remplacé par le thème sombre depuis la barre
de navigation.
