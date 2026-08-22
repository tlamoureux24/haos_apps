# Banc externe de recette — MCB Lot 3B

Cet outil n'est pas intégré à l'add-on. Il appelle le MCP Bridge directement et sert une cible Web jetable permettant de vérifier réellement l'isolation des cookies et de `localStorage`.

Prérequis : port MCP du Bridge publié temporairement, par exemple `8098/tcp → 18098`, et Docker fonctionnel sur le laptop.

```bash
cd mcp_capability_bridge/acceptance/lot3b_external
docker build -t mcb-lot3b-acceptance .
docker run --rm -it --network host mcb-lot3b-acceptance
```

Le programme affiche l'adresse exacte de la fixture. Dans le Bridge, créer ensuite :

- une cible Web temporaire sans authentification vers cette adresse, avec 30 secondes d'inactivité et au moins 300 secondes de durée absolue ;
- deux clients temporaires A et B ;
- les quatre publications Web de la cible vers chacun des clients.

Les credentials sont saisis avec `getpass`, ne sont ni affichés ni écrits. Les handles ne sont jamais imprimés. La rotation et la révocation sont déclenchées manuellement dans l'interface du Bridge lorsque le programme le demande.

Après succès : supprimer la cible temporaire, révoquer puis archiver les clients, arrêter le conteneur et retirer l'exposition du port `18098`.
