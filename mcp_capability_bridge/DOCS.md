# MCP Capability Bridge 0.1.0

## Français

Cette première version fournit uniquement le socle Home Assistant OS du Bridge.

Après installation, ouvrez l’App par Ingress. Le port hôte `8098` est facultatif et ne publie pour le moment que `/health/live` et `/health/ready`. Aucun serveur MCP, credential, client, cible SSH ou cible Web n’est encore disponible.

L’App doit afficher `Prête`, `Santé uniquement` et `Génération 1`. La page de statut confirme que les listeners Ingress 8099 et public 8098 appartiennent au même runtime.

## English

This first release provides only the Home Assistant OS foundation of the Bridge.

After installation, open the App through Ingress. Host port `8098` is optional and currently exposes only `/health/live` and `/health/ready`. No MCP server, credential, client, SSH target or Web target is available yet.

The App should display `Ready`, `Health only` and `Generation 1`. The status drawer confirms that Ingress listener 8099 and public listener 8098 belong to the same runtime.
