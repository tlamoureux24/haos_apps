# Agent Execution Plane 0.2.0

## Français

Après le démarrage, ouvrez l’interface Ingress. La vue d’ensemble confirme que l’App est prête et que le moteur est inactif. La vue Activité affiche uniquement des métadonnées opérationnelles persistantes non sensibles. Les sélecteurs FR/EN et clair/sombre sont mémorisés dans le navigateur.

Le port hôte correspondant au port interne `8098/tcp` se règle dans la section Réseau de l’App. Dans ce Lot 0, seuls `/health/live` et `/health/ready` y existent. Aucun endpoint d’exécution n’est disponible.

La vue **Modèles** permet d’ajouter, valider, modifier, supprimer, activer et ordonner les modèles. Les credentials restent chiffrés et ne sont jamais retournés. La validation OpenAI-compatible peut consommer quelques tokens ; le health automatique n’en consomme aucun.

## English

After startup, open the Ingress UI. Overview confirms that the App is ready and the engine is idle. Activity displays only persistent, non-sensitive operational metadata. Browser-local storage remembers the FR/EN and light/dark selectors.

Configure the host port mapped to internal `8098/tcp` in the App Network section. In Lot 0, only `/health/live` and `/health/ready` exist there. No execution endpoint is available.

The **Models** view adds, validates, edits, deletes, enables, and orders configured models. Credentials remain encrypted and are never returned. OpenAI-compatible validation may consume a few tokens; automatic health consumes none.
