# UniFi Log Explorer

Consultez le [guide français](README.fr.md) ou le [résumé anglais](README.md).

Au premier démarrage, ouvrez l'interface web et créez le compte administrateur.
Configurez ensuite l'UCG pour envoyer IPFIX en UDP `2055` et SIEM/CEF en UDP
`5514` vers l'adresse de Home Assistant. Par défaut, les deux collecteurs
n'acceptent que la source `192.168.1.1`.

Pour tester l'API Traffic Flows, renseignez l'URL HTTPS locale de l'UCG, le site
`default` et une clé API dédiée dans les options, puis redémarrez l'App. La clé
est chiffrée et le champ est automatiquement vidé. Lancez ensuite le test depuis
l'interface web ; un flow au maximum est lu et aucune donnée n'est conservée.

Après un test réussi, activez `flow_collection_enabled` pour archiver les flows
toutes les deux minutes. La collecte utilise pagination, déduplication et
lecture des pages récentes jusqu'aux éléments déjà connus. Une
réparation initiale des dernières 24 heures récupère les lots publiés en retard.
Les données restent bornées par la durée de rétention et la limite
d'enregistrements configurées.
