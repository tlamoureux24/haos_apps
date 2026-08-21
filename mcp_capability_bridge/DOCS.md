# MCP Capability Bridge 0.2.0

## Français

Cette version fournit le serveur MCP multi-client sécurisé du Lot 1. Aucun outil SSH ou Web n’est encore inclus.

Après installation ou mise à jour :

1. ouvrez l’App par Ingress ;
2. créez un client dans **Clients MCP** et copiez immédiatement son credential affiché une seule fois ;
3. configurez le port hôte facultatif `8098` si un client extérieur au réseau interne des Apps doit joindre le Bridge ;
4. utilisez l’URL `http://<hôte>:<port>/mcp` et le credential comme Bearer.

Un client actif découvre actuellement une liste vide, ce qui est normal avant le Lot 2. Les endpoints `/health/live` et `/health/ready` restent publics et non sensibles. Toutes les autres requêtes MCP exigent un credential actif.

Pour la recette HAOS, créez deux clients, vérifiez leurs inventaires vides avec un client MCP générique et avec ACP, renouvelez le premier credential, confirmez que l’ancien est immédiatement refusé, révoquez puis archivez ce client, affichez les archives avec le filtre, redémarrez l’App et vérifiez que seul le nouveau credential du second client reste utilisable. Aucun secret ne doit réapparaître après fermeture du drawer.

## English

This release provides the secure multi-client MCP server from Lot 1. No SSH or Web tool is included yet.

After installation or update:

1. open the App through Ingress;
2. create a client under **MCP clients** and immediately copy its one-time credential;
3. configure optional host port `8098` if a client outside the internal App network must reach the Bridge;
4. use `http://<host>:<port>/mcp` with the credential as a Bearer token.

An active client currently discovers an empty tool list, which is expected before Lot 2. `/health/live` and `/health/ready` remain public and non-sensitive. Every other MCP request requires an active credential.

For HAOS acceptance, create two clients, verify their empty inventories with a generic MCP client and ACP, rotate the first credential, confirm immediate rejection of the old credential, revoke then archive that client, display archived clients through the filter, restart the App and verify that only the second client's credential remains usable. No secret may reappear after closing its drawer.
