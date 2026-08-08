# UniFi Log Explorer

Consultez le [guide français](README.fr.md) ou le [résumé anglais](README.md).

Au premier démarrage, ouvrez l'interface web et créez le compte administrateur.
Configurez ensuite l'UCG pour envoyer IPFIX en UDP `2055` et SIEM/CEF en UDP
`5514` vers l'adresse de Home Assistant. Par défaut, les deux collecteurs
n'acceptent que la source `192.168.1.1`.
