# Agent Execution Plane 0.6.5

## Français

### Intégration Agent Control Plane

Dans **Control Plane**, configurez l’URL du serveur MCP public ACP et le Bearer d’une identité worker limitée à `jobs.claim`, `jobs.heartbeat`, `jobs.complete` et `jobs.fail`. La modification est validée avant enregistrement et le secret est chiffré au repos. Cette configuration reste facultative : le listener standalone et sa readiness ne dépendent jamais d’ACP.

AEP poll toutes les secondes quand le slot est libre et qu’un modèle compatible existe. Le claim ACP fournit l’enveloppe opérationnelle normative : seuls les noms et schémas effectifs de `allowed_capabilities` deviennent des outils modèle. Les outils lifecycle ne le deviennent jamais. Le résultat est persisté avant livraison ; une panne de livraison entraîne un retry identique sans nouvelle inférence. Un restart ne rejoue pas l’exécution.

### Démarrage standalone

1. Configurez au moins un modèle dans **Modèles**. Le caller ne choisit jamais le modèle : AEP utilise l’ordre, les timeouts et le fallback administrateur.
2. Mappez `8098/tcp` dans la section Réseau Home Assistant.
3. Dans **API**, créez le credential et copiez immédiatement le token affiché une seule fois. Seul un verifier one-way est persisté. Rotation invalide l’ancien token ; révocation désactive l’API authentifiée.
4. Soumettez, poll, puis ACK :

```bash
curl -X POST 'http://HOTE:PORT/api/v1/execute' \
 -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' -H 'Content-Type: application/json' \
 --data '{"objective":"Produire le rapport demandé","input":{"id":7},"mcp":{"url":"http://MCP:8000/mcp","bearer_token":"<MCP_BEARER_TOKEN>","tools":[{"name":"read_value","description":"Lire une valeur","input_schema":{"type":"object","properties":{"id":{"type":"integer"}},"required":["id"]}}]},"result_schema":{"type":"object","properties":{"value":{}},"required":["value"]}}'
curl -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' 'http://HOTE:PORT/api/v1/executions/<EXECUTION_ID>'
curl -X POST -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' 'http://HOTE:PORT/api/v1/executions/<EXECUTION_ID>/ack'
```

### Contrat exact

`POST /api/v1/execute` accepte uniquement `objective` (chaîne non vide), `input` (toute valeur JSON, champ obligatoire), `mcp.url` HTTP(S) sans credential embarqué, `mcp.bearer_token` optionnel, `mcp.tools` obligatoire et `result_schema` optionnel. Chaque outil contient exactement `name`, `description`, `input_schema`. Aucun champ model/provider/fallback/instruction additionnelle n’est accepté.

Réponse : `202 {"execution_id":"…","status":"accepted"}` après réservation durable. `GET /api/v1/executions/{id}` retourne `running` ou `result_available` et ne libère rien. `POST .../{id}/ack` supprime uniquement le pending correspondant et retourne `acknowledged`.

| HTTP | Code JSON | Signification |
|---:|---|---|
| 400 | `malformed_json` | JSON illisible |
| 401 | `unauthenticated` | Bearer absent/invalide |
| 404 | `execution_not_found` | ID absent, acquitté ou abandonné |
| 409 | `busy_active` | exécution active |
| 409 | `busy_pending_result` | résultat non acquitté |
| 409 | `result_not_available` | ACK avant résultat |
| 413 | `body_too_large` | request > 4 Mio |
| 422 | `invalid_execution_contract` | structure, URL, schéma ou limite invalide |
| 503 | `credential_not_configured` | aucun credential standalone |

Un échec modèle/MCP survenant après le `202` devient un outcome technique pending, jamais une erreur rétroactive du POST.

### Slot, restart et confidentialité

Une seule référence `active_execution` ou un seul `pending_result` existe. Il n’y a aucune queue. Un GET peut être répété à l’identique ; l’absence d’ACK bloque volontairement toute nouvelle exécution. L’action Ingress confirmée **Abandonner le résultat en attente** inclut l’ID affiché et ne supprime rien si le pending a changé.

Après restart, un pending est conservé exactement. Une active standalone devient `execution_interrupted` pour le même ID sans replay. Seuls l’ID, la source et les timestamps sont persistés pendant active. Le pending contient l’outcome nécessaire à la livraison. Objectif, input, endpoint/Bearer MCP, outils, arguments/résultats MCP, conversation et raisonnement ne sont jamais persistés ou journalisés. Après ACK/abandon, aucun historique terminé ne reste.

## English

### Agent Control Plane integration

In **Control Plane**, configure ACP's public MCP server URL and the Bearer for a worker identity limited to `jobs.claim`, `jobs.heartbeat`, `jobs.complete`, and `jobs.fail`. Changes are validated before storage and the credential is encrypted at rest. Configuration is optional: standalone operation and App readiness never depend on ACP.

AEP polls every second while the slot is free and a compatible model exists. The ACP claim supplies the normative operational envelope: only effective names and schemas in `allowed_capabilities` become model tools; lifecycle tools never do. The outcome is persisted before delivery, delivery failures retry the identical outcome without another inference, and restart never replays execution.

### Standalone setup

1. Configure at least one model in **Models**. The caller never selects it; AEP applies administrator order, timeout, and fallback.
2. Map `8098/tcp` in Home Assistant Network settings.
3. In **API**, create the credential and immediately copy the one-time token. Only a salted one-way verifier persists. Rotation invalidates the old token; revocation disables authenticated API calls.
4. Submit, poll, then ACK:

```bash
curl -X POST 'http://HOST:PORT/api/v1/execute' \
 -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' -H 'Content-Type: application/json' \
 --data '{"objective":"Produce the requested report","input":{"id":7},"mcp":{"url":"http://MCP:8000/mcp","bearer_token":"<MCP_BEARER_TOKEN>","tools":[{"name":"read_value","description":"Read one value","input_schema":{"type":"object","properties":{"id":{"type":"integer"}},"required":["id"]}}]},"result_schema":{"type":"object","properties":{"value":{}},"required":["value"]}}'
curl -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' 'http://HOST:PORT/api/v1/executions/<EXECUTION_ID>'
curl -X POST -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' 'http://HOST:PORT/api/v1/executions/<EXECUTION_ID>/ack'
```

### Exact contract

`POST /api/v1/execute` accepts only a non-empty string `objective`, required `input` containing any JSON value, HTTP(S) `mcp.url` without embedded credentials, optional `mcp.bearer_token`, required `mcp.tools`, and optional `result_schema`. Every tool contains exactly `name`, `description`, and `input_schema`. Model/provider/fallback/extra-instruction fields are rejected.

It returns `202 {"execution_id":"…","status":"accepted"}` only after durable reservation. `GET /api/v1/executions/{id}` returns `running` or `result_available` and never releases state. `POST .../{id}/ack` deletes only the matching pending result and returns `acknowledged`.

| HTTP | JSON code | Meaning |
|---:|---|---|
| 400 | `malformed_json` | unreadable JSON |
| 401 | `unauthenticated` | missing/invalid Bearer |
| 404 | `execution_not_found` | unknown, acknowledged, or abandoned ID |
| 409 | `busy_active` | active execution |
| 409 | `busy_pending_result` | unacknowledged result |
| 409 | `result_not_available` | ACK before result |
| 413 | `body_too_large` | request over 4 MiB |
| 422 | `invalid_execution_contract` | invalid structure, URL, schema, or bound |
| 503 | `credential_not_configured` | no standalone credential |

Model/MCP failures after `202` become pending technical outcomes, never retroactive POST errors.

### Slot, restart, and confidentiality

Only one `active_execution` or one `pending_result` exists; there is no queue. GET is repeatable, and missing ACK intentionally blocks new submissions. The confirmed Ingress **Abandon pending result** action carries the displayed ID and deletes nothing if pending state changed.

Restart preserves a pending result exactly. A standalone active reference becomes `execution_interrupted` under the same ID without replay. Active persistence contains only ID/source/timestamp; pending stores only the deliverable outcome. Objective, input, MCP endpoint/Bearer/tools/arguments/results, conversation, and reasoning are never persisted or journaled. ACK/abandonment leaves no completed history.
