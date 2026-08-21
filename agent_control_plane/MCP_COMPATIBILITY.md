# Agent Control Plane — MCP compatibility / Compatibilité MCP

[Français](#français) | [English](#english)

## Français

### Portée

Cette déclaration décrit la compatibilité réellement visée par la branche stable
actuelle d’Agent Control Plane. Elle distingue les fonctions prises en charge par le
SDK MCP épinglé de celles directement exercées par la CI d’Agent Control Plane ; elle
ne constitue pas une certification de conformité complète au protocole MCP.

La version actuelle d’Agent Control Plane utilise `mcp==1.28.1` pour son serveur MCP
public et pour ses connexions MCP amont.

### Transports et rôles

| Rôle Agent Control Plane | Transport pris en charge | Authentification | Fonctions MCP utilisées |
| --- | --- | --- | --- |
| Serveur public pour les agents | Streamable HTTP sur `/mcp` | Bearer Agent Control Plane obligatoire | `initialize`, `tools/list`, `tools/call`, notifications `tools/list_changed` |
| Client vers les connecteurs amont | Streamable HTTP sur une URL `http` ou `https` configurée par l’administrateur | Bearer facultatif, stocké uniquement dans la passerelle | `initialize`, `tools/list`, `tools/call` |

Les connecteurs `stdio`, le transport SSE historique et les autres transports
MCP ne sont pas pris en charge. Agent Control Plane ne proxifie pas les ressources,
prompts, roots, sampling, elicitation, completions ou logging d’un serveur amont :
le contrat de connecteur actuel porte uniquement sur les outils.

Le serveur public est stateless au niveau HTTP. Il conserve une réponse
Streamable HTTP sous forme SSE lorsque cela est nécessaire pour transmettre les
notifications dynamiques de changement de liste d’outils après une réclamation,
une fin ou un échec de travail.

Les outils lifecycle worker sont `jobs_claim_v1`, `jobs_heartbeat_v1`,
`jobs_complete_v1` et `jobs_fail_v1`. Les deux opérations terminales exigent une
`completion_key` opaque. ACP conserve cette clé avec la tentative : répéter le
même appel après une réponse réseau perdue restitue l’état déjà enregistré sans
appliquer une seconde transition.

### Révisions du protocole

Le SDK Python MCP 1.28.1 utilisé par Agent Control Plane annonce les révisions prises
en charge suivantes :

- `2024-11-05` ;
- `2025-03-26` ;
- `2025-06-18` ;
- `2025-11-25`.

Sa révision la plus récente est `2025-11-25`. Agent Control Plane délègue la
négociation `initialize` à ce SDK et n’ajoute pas de mécanisme de négociation
propriétaire.

La CI d’Agent Control Plane exerce directement son listener public avec une requête
`initialize` en `2025-06-18`, vérifie qu’un appel non authentifié est refusé et
qu’un appel authentifié obtient bien une réponse du serveur Agent Control Plane. Les
autres révisions ci-dessus sont donc supportées par la dépendance MCP épinglée,
mais ne sont pas présentées comme individuellement couvertes par un test de
conformité Agent Control Plane.

La révision MCP `2026-07-28` n’est pas revendiquée par cette branche : elle
nécessite la génération suivante du SDK et ne fait pas partie de
`mcp==1.28.1`.

### Contrat des connecteurs

Une URL de connecteur doit utiliser `http` ou `https`, comporter un hôte valide,
ne pas contenir d’identifiants intégrés ni de fragment, et rester sous 2048
caractères. Les redirections HTTP ne sont pas suivies. Un connecteur peut
utiliser un Bearer fourni explicitement par l’administrateur ; Agent Control Plane ne
met pas en œuvre OAuth pour les connecteurs dans cette version.

La découverte est bornée à 200 outils par connecteur. Le schéma d’entrée de
chaque outil est limité à 16 Kio encodés et doit être admis par le profil JSON
Schema Draft 2020-12 fail-closed d’Agent Control Plane, avec références locales
uniquement et mots-clés/formats explicitement reconnus. Un résultat amont est
limité à 256 Kio avant remise au client.

L’ajout ou la découverte d’un outil ne lui donne aucun droit d’exécution. Il ne
devient invocable qu’après sélection explicite dans une révision de tâche valide,
avec vérification du connecteur, du nom d’outil, de l’empreinte du schéma, de
l’identité appelante, du lease actif, du schéma effectif et des éventuels
`fixed_arguments_v1`.

### Compatibilité testée et limites

Le dépôt fournit `scripts/fake_mcp_server.py`, un serveur Streamable HTTP en
lecture seule basé sur le même SDK épinglé, pour les recettes de connecteurs et
de collisions de noms d’outils. Ce serveur de recette n’est pas une suite de
conformité MCP.

Agent Control Plane ne revendique actuellement ni OAuth MCP, ni connecteurs `stdio`,
ni SSE historique, ni haute disponibilité multi-instance, ni exposition directe
sur Internet. Le listener public doit être publié seulement sur un LAN ou VPN de
confiance lorsque son accès direct est nécessaire.

Sources d’implémentation : `requirements.txt`, `src/agent_control_plane/connectors.py`,
`src/agent_control_plane/mcp_api.py`, `src/agent_control_plane/json_contracts.py` et le smoke
test de `.github/workflows/agent-control-plane-validate.yml`.

## English

### Scope

This statement describes the compatibility actually targeted by the current
stable Agent Control Plane branch. It distinguishes capabilities inherited from the
pinned MCP SDK from behavior directly exercised by Agent Control Plane CI; it is not a
claim of full MCP conformance certification.

The current Agent Control Plane release uses `mcp==1.28.1` for both its public MCP
server and its upstream MCP client connections.

### Transports and roles

| Agent Control Plane role | Supported transport | Authentication | MCP operations used |
| --- | --- | --- | --- |
| Public server for agents | Streamable HTTP on `/mcp` | Agent Control Plane Bearer required | `initialize`, `tools/list`, `tools/call`, `tools/list_changed` notifications |
| Client to upstream connectors | Streamable HTTP to an administrator-configured `http` or `https` URL | Optional Bearer kept inside the gateway | `initialize`, `tools/list`, `tools/call` |

`stdio` connectors, the legacy SSE transport, and other MCP transports are not
supported. Agent Control Plane does not proxy upstream resources, prompts, roots,
sampling, elicitation, completions, or logging: the current connector contract
is tool-only.

The public server is HTTP-stateless. It keeps a Streamable HTTP response as SSE
when required to deliver dynamic tool-list change notifications after job claim,
completion, or failure.

The worker lifecycle tools are `jobs_claim_v1`, `jobs_heartbeat_v1`,
`jobs_complete_v1`, and `jobs_fail_v1`. Both terminal operations require an
opaque `completion_key`. ACP stores that key with the attempt, so replaying the
same call after a lost network response returns the recorded state without a
second transition.

### Protocol revisions

The MCP Python SDK 1.28.1 pinned by Agent Control Plane advertises support for these
protocol revisions:

- `2024-11-05`;
- `2025-03-26`;
- `2025-06-18`;
- `2025-11-25`.

Its latest revision is `2025-11-25`. Agent Control Plane delegates `initialize`
negotiation to that SDK and adds no proprietary negotiation layer.

Agent Control Plane CI directly exercises the public listener with a `2025-06-18`
`initialize` request, verifies that an unauthenticated request is rejected, and
that an authenticated request receives an Agent Control Plane server response. The
other revisions above are therefore supported by the pinned MCP dependency but
are not claimed as individually covered by an Agent Control Plane conformance test.

MCP revision `2026-07-28` is not claimed by this branch: it requires the next SDK
generation and is outside `mcp==1.28.1`.

### Connector contract

A connector URL must use `http` or `https`, contain a valid host, contain no
embedded credentials or fragment, and remain within 2048 characters. HTTP
redirects are not followed. A connector may use a Bearer token explicitly
supplied by the administrator; Agent Control Plane does not implement connector OAuth
in this release.

Discovery is bounded to 200 tools per connector. Each tool input schema is
limited to 16 KiB encoded and must be admitted by Agent Control Plane's fail-closed
JSON Schema Draft 2020-12 profile, with local references only and explicitly
recognized keywords and formats. An upstream result is limited to 256 KiB
before delivery to the client.

Adding or discovering a tool grants no execution right. It becomes invocable
only after explicit selection in a valid task revision, with connector, tool
name, schema fingerprint, caller identity, active lease, effective schema, and
optional `fixed_arguments_v1` restrictions all revalidated.

### Tested compatibility and limits

The repository ships `scripts/fake_mcp_server.py`, a harmless read-only
Streamable HTTP server based on the same pinned SDK, for connector and duplicate
tool-name acceptance work. It is an acceptance fixture, not an MCP conformance
suite.

Agent Control Plane currently claims no MCP OAuth, `stdio` connectors, legacy SSE
transport, multi-instance high availability, or direct Internet exposure. The
public listener should be published only on a trusted LAN or VPN when direct
access is required.

Implementation evidence: `requirements.txt`, `src/agent_control_plane/connectors.py`,
`src/agent_control_plane/mcp_api.py`, `src/agent_control_plane/json_contracts.py`, and the
smoke test in `.github/workflows/agent-control-plane-validate.yml`.
