# Agent Execution Plane 0.3.1

## Français

### Rôle

Agent Execution Plane est uniquement le moteur de raisonnement et d’exécution. Il ne gouverne pas les tâches, les connecteurs MCP ni les capacités autorisées.

Lorsque Agent Control Plane est utilisé, ACP reste l’unique autorité : il possède les connecteurs MCP amont, sélectionne les outils dans les tâches, construit les capacités virtuelles et leurs schémas effectifs, applique les restrictions telles que `fixed_arguments_v1`, puis réautorise/résout chaque invocation côté ACP.

Après `jobs_claim_v1`, le champ `job.allowed_capabilities` fourni par ACP est l’enveloppe autoritaire des capacités invocables par le modèle. AEP peut vérifier techniquement que ces capacités existent toujours avec le schéma attendu, mais il ne choisit jamais une autre liste à partir du `tools/list` complet du serveur ACP.

Le même serveur MCP ACP expose aussi des outils de cycle de vie utilisés uniquement par la frontière AEP, notamment claim, heartbeat, complete et fail. Ils ne sont jamais rendus visibles au modèle simplement parce que l’identité worker peut les appeler.

En standalone futur, le caller fournit lui-même l’enveloppe exacte des capacités MCP du modèle. AEP conserve exactement le même rôle : vérifier techniquement et exécuter, jamais autoriser ou sélectionner.

### Utilisation actuelle

Après le démarrage, ouvrez l’interface Ingress. La vue d’ensemble confirme que l’App est prête et que le moteur est inactif. La vue Activité affiche uniquement des métadonnées opérationnelles persistantes non sensibles. Les sélecteurs FR/EN et clair/sombre sont mémorisés dans le navigateur.

Le port hôte correspondant au port interne `8098/tcp` se règle dans la section Réseau de l’App. À ce stade, seuls `/health/live` et `/health/ready` y existent. Aucun endpoint d’exécution n’est encore disponible.

La vue **Modèles** permet d’ajouter, valider, modifier, supprimer, activer et ordonner les modèles. Les credentials restent chiffrés et ne sont jamais retournés. La validation OpenAI-compatible peut consommer quelques tokens ; le health automatique n’en consomme aucun.

La famille **OpenAI ChatGPT OAuth** utilise le flow officiel device-code du runtime Codex `0.144.4`. Elle n’accepte ni URL de base ni clé API. Le compte ChatGPT est partagé entre les modèles OAuth et ses tokens restent exclusivement dans `/data/private/codex-home` sous le contrôle de Codex.

Le Lot 2 ajoute uniquement le moteur d’exécution source-neutral. L’intégration ACP complète, y compris claim/lease/heartbeat/result delivery, appartient au Lot 4 et doit consommer le contrat ACP existant sans recréer sa gouvernance.

## English

### Role

Agent Execution Plane is only the reasoning and execution engine. It does not govern tasks, MCP connectors, or authorized capabilities.

When Agent Control Plane is used, ACP remains the sole authority: it owns upstream MCP connectors, selects tools in tasks, constructs virtual capabilities and effective schemas, applies restrictions such as `fixed_arguments_v1`, and reauthorizes/resolves each invocation inside ACP.

After `jobs_claim_v1`, ACP's `job.allowed_capabilities` field is the authoritative model-invocable capability envelope. AEP may technically verify that those capabilities still exist with the expected schema, but it never chooses a different list from the ACP server's complete `tools/list` inventory.

The same ACP MCP server also exposes lifecycle tools used only by the AEP source boundary, including claim, heartbeat, complete and fail. They are never made model-visible merely because the worker identity can call them.

In future standalone operation, the caller supplies the exact model MCP capability envelope. AEP keeps the same role: technically verify and execute, never authorize or select.

### Current operation

After startup, open the Ingress UI. Overview confirms that the App is ready and the engine is idle. Activity displays only persistent, non-sensitive operational metadata. Browser-local storage remembers the FR/EN and light/dark selectors.

Configure the host port mapped to internal `8098/tcp` in the App Network section. At this stage, only `/health/live` and `/health/ready` exist there. No execution endpoint is available yet.

The **Models** view adds, validates, edits, deletes, enables, and orders configured models. Credentials remain encrypted and are never returned. OpenAI-compatible validation may consume a few tokens; automatic health consumes none.

The **OpenAI ChatGPT OAuth** family uses the official device-code flow from Codex runtime `0.144.4`. It accepts neither a base URL nor an API key. The ChatGPT account is shared by OAuth models and its tokens remain exclusively under Codex control in `/data/private/codex-home`.

Lot 2 adds only the source-neutral execution engine. Full ACP integration, including claim/lease/heartbeat/result delivery, belongs to Lot 4 and must consume the existing ACP contract without recreating its governance.