# Agent Execution Plane

Agent Execution Plane `1.0.2` est un moteur de raisonnement et d’exécution utilisable en mode autonome. Il applique la priorité administrateur des modèles et les règles communes de fallback/non-replay à l’enveloppe exacte des capacités opérationnelles MCP fournie par la source courante.

## Frontière de responsabilité

AEP ne possède ni tâches, ni configuration de connecteurs, ni sélection/autorisation de capacités, ni planification, ni historique d’exécution. Le caller standalone fournit l’objectif, l’input JSON, un endpoint MCP et son Bearer optionnel limités à l’exécution, les descripteurs exacts des outils MCP et un schéma de résultat optionnel. Le caller ne peut pas choisir le modèle. `tools/list` sert uniquement à vérifier les descripteurs fournis et ne peut jamais les élargir.

Les aides natives provider de planification/information publique restent séparées des outils MCP opérationnels et ne peuvent accéder ni à l’infrastructure utilisateur ni à l’état privé AEP.

## Frontière Agent Control Plane

La vue facultative **Control Plane** accepte une URL MCP Streamable HTTP et le credential Bearer protégé d’une identité worker. AEP valide les outils de cycle de vie ACP existants avant enregistrement, puis interroge `jobs_claim_v1` chaque seconde uniquement lorsqu’un modèle compatible et le slot partagé sont disponibles. ACP reste seul responsable des jobs, leases, connecteurs, arguments fixes, autorisations de capacités, retries et politique de rapport.

Pour chaque claim, AEP transmet `objective`, `input`, `required_report_schema` et exactement `allowed_capabilities` au même moteur que l’API autonome. Les outils de cycle de vie ACP et les outils étrangers découverts par `tools/list` ne sont jamais exposés au modèle. AEP maintient le heartbeat, bloque tout nouveau dispatch MCP après perte du lease, persiste l’outcome avant `jobs_complete_v1`/`jobs_fail_v1`, retente la livraison sans rejouer le modèle et réconcilie une interruption après restart. L’indisponibilité ACP ne dégrade jamais `/health/ready` et l’absence de configuration Control Plane conserve intégralement le mode autonome.

La validation de connexion vérifie les signatures d’entrée des outils lifecycle, et pas seulement leurs noms. La livraison d’échec conserve la même clé de complétion à chaque tentative ; une erreur heartbeat transitoire consécutive est tolérée, la seconde arrête l’exécution. Au redémarrage, un lease persisté déjà expiré est libéré localement afin de ne jamais retenir le slot partagé AEP.

AEP conserve exactement une connexion Control Plane facultative. La vue d’ensemble affiche son état opérationnel sûr, le dernier poll de claim réussi, la dernière réponse ACP, la disponibilité `0`/`1` issue de ce claim, le compteur de polls réussis et la dernière erreur bornée. Modifier la connexion remplace ce singleton après validation ; cela ne crée jamais une seconde source ACP.

## Installation et configuration

Installez l’App, configurez un ou plusieurs modèles dans Ingress, puis mappez le port interne `8098/tcp` vers le port hôte souhaité dans la section **Réseau** de l’App Home Assistant. L’administration reste exclusivement accessible par Ingress sur le port interne `8099`.

Ouvrez la vue **API** puis choisissez **Créer le credential**. Copiez immédiatement le token opaque : seul un verifier one-way est conservé et le token clair ne peut plus être récupéré. **Renouveler** invalide immédiatement l’ancien token ; **Révoquer** désactive les appels standalone authentifiés. Le journal Activité n’enregistre jamais ces tokens.

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

## Guide de configuration détaillé

### Surfaces réseau

| Surface | Port interne | Exposition | Contenu |
|---|---:|---|---|
| Administration | `8099` | Ingress uniquement | Vue d’ensemble, Activité, Modèles, API et Control Plane |
| Autonome | `8098` | Mapping hôte facultatif | `/health/live`, `/health/ready` et `/api/v1/*` |

Mappez `8098/tcp` uniquement si un appelant autonome en a besoin. Les exemples HTTP actuels ne chiffrent pas les Bearers pendant le transport : restez sur un réseau isolé de confiance ou placez un reverse proxy TLS fiable devant AEP.

### Familles de modèles

- **Compatible Ollama** : URL de base, identifiant exact, timeout positif et credential facultatif. Exemple : `http://192.168.1.20:11434`, `qwen3:14b`.
- **Compatible OpenAI** : URL compatible, identifiant exact, timeout et credential. L’enregistrement effectue un probe explicite pouvant consommer des tokens ou crédits.
- **ChatGPT OAuth** : lancez la connexion par appareil, ouvrez l’URL affichée, entrez le code temporaire, attendez l’état `connected`, puis créez un modèle depuis le catalogue validé. Les données OAuth restent privées dans AEP.

La priorité `1` est essayée en premier. L’appelant ne choisit jamais le modèle. Un modèle en cours d’utilisation ne peut pas être modifié, désactivé ou supprimé ; son ordre peut toujours être changé sans affecter l’exécution courante.

### Configurer le worker ACP

1. Créez une identité ACP de type **Client MCP** dédiée au rôle de worker.
2. Accordez-lui uniquement `jobs.claim`, `jobs.heartbeat`, `jobs.complete` et `jobs.fail` ; ce sont ces permissions qui définissent le rôle de worker.
3. Copiez son credential Bearer affiché une seule fois.
4. Dans **Control Plane** d’AEP, saisissez l’endpoint complet, par exemple `https://IP_HOME_ASSISTANT:8100/mcp`.
5. Collez le credential worker et enregistrez.

Si ACP utilise son certificat autogénéré, saisissez aussi son empreinte SHA-256
vérifiée indépendamment. Laissez le champ vide pour un certificat validé par les
CA du système. L’API autonome AEP utilise HTTPS par défaut ; son empreinte et la
régénération sont disponibles dans l’administration Ingress.

AEP valide les noms et les schémas d’entrée des outils de cycle de vie. Lors d’une modification, laissez le credential vide pour conserver le secret chiffré existant. AEP ne poll que si le slot et un modèle compatible sont disponibles. `allowed_capabilities` fourni par ACP est normatif ; les outils de cycle de vie et l’inventaire étranger ne deviennent jamais visibles par le modèle.

## Écrire le JSON autonome

Pour éviter une ligne shell illisible, placez la requête dans `request.json` :

```json
{
  "objective": "Lire la métrique demandée et produire un rapport JSON.",
  "input": {
    "site": "principal",
    "metric": "temperature"
  },
  "mcp": {
    "url": "http://192.168.1.50:8765/mcp",
    "bearer_token": "REMPLACER_PAR_LE_TOKEN_MCP",
    "tools": [
      {
        "name": "read_metric",
        "description": "Lire une métrique pour un site",
        "input_schema": {
          "type": "object",
          "properties": {
            "site": {"type": "string"},
            "name": {"type": "string"}
          },
          "required": ["site", "name"],
          "additionalProperties": false
        }
      }
    ]
  },
  "result_schema": {
    "type": "object",
    "properties": {
      "site": {"type": "string"},
      "metric": {"type": "string"},
      "value": {"type": "number"},
      "unit": {"type": "string"}
    },
    "required": ["site", "metric", "value", "unit"],
    "additionalProperties": false
  }
}
```

Règles provoquant souvent `invalid_execution_contract` :

- `objective` doit être une chaîne non vide ;
- `input` est obligatoire mais accepte toute valeur JSON, y compris `null`, un tableau ou un objet ;
- `mcp.url` doit être HTTP(S), sans utilisateur/mot de passe intégré ;
- `bearer_token` est facultatif et doit être omis s’il est inutile ;
- `tools` est obligatoire et peut être vide : c’est l’enveloppe exacte d’autorisation ;
- chaque outil contient exactement `name`, `description` et `input_schema` ;
- les champs modèle/provider/fallback et les champs racine inconnus sont refusés.

Le descripteur doit correspondre à l’entrée réelle de `tools/list`. La découverte vérifie le nom et le schéma fournis sans jamais élargir la liste.

Validez puis envoyez :

```bash
jq . request.json

curl -X POST 'http://IP_HOME_ASSISTANT:PORT_AEP/api/v1/execute' \
  -H 'Authorization: Bearer REMPLACER_PAR_LE_TOKEN_AEP' \
  -H 'Content-Type: application/json' \
  --data-binary @request.json
```

Réponse d’acceptation attendue :

```json
{"execution_id":"019c...","status":"accepted"}
```

Interrogez jusqu’à disponibilité, traitez durablement le résultat, puis envoyez l’ACK. GET est répétable ; seul l’ACK libère le slot.

## Cycle de vie, outcomes et dépannage

```text
inactif → actif → résultat en attente → ACK → inactif
```

Il n’existe aucune file cachée. Un redémarrage conserve un outcome pending à l’identique ; une exécution autonome interrompue devient `execution_interrupted` sans replay. Pour ACP, AEP réconcilie le lease et retente la livraison avec la même clé de complétion sans relancer l’inférence.

Si `mcp_effect_possible` vaut `true`, la cible a pu appliquer l’effet même si AEP a perdu la réponse. Ne programmez jamais un retry automatique uniquement à partir du code d’échec.

| Symptôme | Vérification |
|---|---|
| Modèle indisponible | Réseau provider, identifiant exact, credential, timeout, compte/catalogue OAuth |
| Connexion ACP refusée | URL complète `/mcp`, Bearer, quatre permissions worker, schémas compatibles |
| `invalid_execution_contract` | `jq .`, clés inconnues, champs outil requis, égalité avec `tools/list` |
| `busy_pending_result` | Interroger l’ID affiché puis ACK après consommation durable |
| Échec MCP répété | Schéma, cible, Bearer et `mcp_effect_possible` avant tout retry |

Activité exclut volontairement objectifs, entrées, credentials, arguments/résultats, conversations et raisonnement. Les secrets modèles/ACP sont chiffrés au repos ; le token autonome n’est conservé que sous forme de vérificateur irréversible.
