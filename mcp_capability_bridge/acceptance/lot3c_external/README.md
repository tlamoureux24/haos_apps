# Banc externe de recette — MCB Lot 3C

Ce banc n'est pas intégré à l'App. Il sert deux cibles Web jetables et appelle directement le port MCP temporairement publié du Bridge. Il ne touche ni à ACP ni à AEP.

```bash
cd mcp_capability_bridge/acceptance/lot3c_external
docker build -t mcb-lot3c-acceptance .
docker run --rm -it --network host mcb-lot3c-acceptance
```

Le programme affiche deux URL. Créer dans le Bridge :

- une cible `Reader` en authentification Basic avec `reader` / `reader-secret` ;
- une cible `Admin` en authentification Basic avec `admin` / `admin-secret` ;
- un client MCP temporaire ;
- pour `Reader`, publier `open`, `click` et `close` ;
- pour `Admin`, publier les neuf outils Web.

Les clés techniques des deux cibles et le credential MCP sont ensuite saisis dans le terminal. Le credential est masqué, jamais écrit ni affiché. Le runner vérifie automatiquement l'autorité réelle des comptes, les actions bornées, les références périmées, la sérialisation et les principales protections de confinement.

Après succès, supprimer les deux cibles, révoquer puis archiver le client temporaire, et retirer l'exposition du port `18098`.
