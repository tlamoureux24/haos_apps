# Agent Execution Plane

Agent Execution Plane `0.5.0` est un moteur de raisonnement et d’exécution utilisable en mode autonome. Il applique la priorité administrateur des modèles et les règles de fallback/non-replay du Lot 2 à l’enveloppe exacte des capacités opérationnelles MCP fournie par la source courante.

## Frontière de responsabilité

AEP ne possède ni tâches, ni configuration de connecteurs, ni sélection/autorisation de capacités, ni planification, ni historique d’exécution. Le caller standalone fournit l’objectif, l’input JSON, un endpoint MCP et son Bearer optionnel limités à l’exécution, les descripteurs exacts des outils MCP et un schéma de résultat optionnel. Le caller ne peut pas choisir le modèle. `tools/list` sert uniquement à vérifier les descripteurs fournis et ne peut jamais les élargir.

Les aides natives provider de planification/information publique restent séparées des outils MCP opérationnels et ne peuvent accéder ni à l’infrastructure utilisateur ni à l’état privé AEP. L’intégration ACP n’est pas implémentée dans ce lot.

## Installation et configuration

Installez l’App, configurez un ou plusieurs modèles dans Ingress, puis mappez le port interne `8098/tcp` vers le port hôte souhaité dans la section **Réseau** de l’App Home Assistant. L’administration reste exclusivement accessible par Ingress sur le port interne `8099`.

Ouvrez la vue **API** puis choisissez **Créer le credential**. Copiez immédiatement le token opaque : seul un verifier PBKDF2 est conservé et le token clair ne peut plus être récupéré. **Renouveler** invalide immédiatement l’ancien token ; **Révoquer** désactive les appels standalone authentifiés. Le journal Activité n’enregistre jamais ces tokens.

## API autonome

Toutes les routes d’exécution exigent `Authorization: Bearer <AEP_STANDALONE_TOKEN>`. Les routes health restent publiques et non sensibles.

```bash
curl -X POST 'http://HOTE_HOME_ASSISTANT:PORT_AEP/api/v1/execute' \
  -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' \
  -H 'Content-Type: application/json' \
  --data '{
    "objective":"Lire la métrique demandée et retourner un rapport JSON.",
    "input":{"site":"exemple"},
    "mcp":{
      "url":"http://HOTE_MCP:8000/mcp",
      "bearer_token":"<MCP_BEARER_TOKEN>",
      "tools":[{"name":"read_metric","description":"Lire une métrique","input_schema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}}]
    },
    "result_schema":{"type":"object","properties":{"value":{}},"required":["value"]}
  }'
```

Une soumission valide retourne HTTP `202` avec un `execution_id` opaque. Le polling ne libère pas le slot :

```bash
curl -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' \
  'http://HOTE_HOME_ASSISTANT:PORT_AEP/api/v1/executions/<EXECUTION_ID>'
```

Après réception durable du résultat, acquittez-le :

```bash
curl -X POST -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' \
  'http://HOTE_HOME_ASSISTANT:PORT_AEP/api/v1/executions/<EXECUTION_ID>/ack'
```

GET est répétable et ne libère jamais le slot. Avant ACK, une nouvelle soumission retourne `busy_pending_result`. Une exécution active retourne `busy_active`. Pour abandonner volontairement la livraison, l’Overview Ingress propose l’action confirmée **Abandonner le résultat en attente**, liée à l’ID affiché.

## Durabilité et sécurité

La base conserve seulement une référence active minimale ou un résultat pending. Objectif, input, URL/Bearer MCP, descripteurs, arguments/résultats d’outils, prompts, conversation et raisonnement restent uniquement en mémoire pendant l’exécution. Le résultat final n’existe que dans `pending_result` jusqu’à ACK/abandon ; aucun historique terminé n’est conservé.

Après restart, un résultat pending est rendu à l’identique. Une exécution standalone restée active devient `execution_interrupted` pour le même ID et n’est jamais rejouée. Les documents request et API résultat sont limités à 4 Mio ; les limites Lot 2 de 128 capacités/dispatchs, 512 Kio d’arguments et 2 Mio par résultat d’outil restent appliquées sans troncature.

L’interface est bilingue FR/EN, claire/sombre et conserve le gutter global stable. Consultez [README.md](README.md) pour l’anglais et [DOCS.md](DOCS.md) pour la table complète des statuts API.
