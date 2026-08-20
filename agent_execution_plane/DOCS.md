# Agent Execution Plane 0.1.2

## Français

Après le démarrage, ouvrez l’interface Ingress. La vue d’ensemble confirme que l’App est prête et que le moteur est inactif. La vue Activité affiche uniquement des métadonnées opérationnelles persistantes non sensibles. Les sélecteurs FR/EN et clair/sombre sont mémorisés dans le navigateur.

Le port hôte correspondant au port interne `8098/tcp` se règle dans la section Réseau de l’App. Dans ce Lot 0, seuls `/health/live` et `/health/ready` y existent. Aucun endpoint d’exécution n’est disponible.

## English

After startup, open the Ingress UI. Overview confirms that the App is ready and the engine is idle. Activity displays only persistent, non-sensitive operational metadata. Browser-local storage remembers the FR/EN and light/dark selectors.

Configure the host port mapped to internal `8098/tcp` in the App Network section. In Lot 0, only `/health/live` and `/health/ready` exist there. No execution endpoint is available.
