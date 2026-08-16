# Agent Gateway — threat model / Modèle de menace

[Français](#français) | [English](#english)

## Français

### Portée et principe d’autorisation

Agent Gateway est un pare-feu applicatif générique pour MCP. Son modèle de
sécurité est **deny-by-default** : la configuration explicite de
l’administrateur constitue l’autorisation. La découverte d’un outil n’accorde
aucun droit ; un outil devient utilisable seulement lorsqu’il est sélectionné
dans une révision de tâche valide, puis uniquement dans l’enveloppe exacte
formée par la tâche, le connecteur, l’outil, son empreinte de schéma, l’identité
appelante, le lease actif, le schéma effectif et les éventuelles restrictions
`fixed_arguments_v1`.

Les étiquettes sémantiques telles que `read`, `write`, `admin`, `safe` ou
`dangerous` ne sont **pas** des classes d’autorisation. Un outil capable de
modifier un système amont, s’il est explicitement sélectionné par
l’administrateur, est gouverné par les mêmes contrôles qu’un outil de lecture.
Agent Gateway n’ajoute pas de seconde approbation transactionnelle ou de moteur
de risque qui contredirait cette décision administrative.

Ce document décrit les frontières réellement implémentées. Les preuves marquées
**Automatique** sont exercées par les tests Python ou la CI ; **HAOS** désigne
une recette manuelle déjà exécutée sur l’App réelle ; **À compléter** identifie
un gate de release qui reste à matérialiser.

### Matrice des frontières

| Frontière | Menace considérée | Contrôle appliqué | Preuve actuelle |
| --- | --- | --- | --- |
| Installation propre → capacités | Un connecteur, fournisseur, domaine de tâche ou outil puissant serait activé implicitement | Le schéma frais ne crée aucun connecteur, aucune tâche ni identité ; `8098` n’est pas publié par défaut ; aucune dépendance HA-MCP/Gatus n’est configurée dans l’App | **Automatique** — `database.py`, `config.yaml`, `scripts/validate.py`, smoke CI : zéro connecteur/tâche au démarrage |
| Navigateur administrateur → listener d’administration | Accès direct à l’API admin, contournement d’Ingress ou requête de mutation forgée | Listener admin séparé ; IP du proxy Ingress exigée ; contexte `X-Ingress-Path` exigé ; mutations protégées par cookie+header CSRF comparés en temps constant ; CSP, `no-store`, `nosniff`, `no-referrer` | **Automatique** — `main.py`, `http_api.py`, `surfaces.py`, tests de surface et smoke CI |
| Client réseau → surface publique MCP/événements | Appel sans identité, credential malformé/forgé/révoqué ou escalade d’action | Bearer opaque ; secret non stocké en clair, vérificateur HMAC avec pepper ; révocation des credentials ; permissions explicites et deny-by-default ; listener public ne contient aucune route d’administration | **Automatique** — `security.py`, `policy.py`, `mcp_api.py`, `surfaces.py`, `CredentialTests`, `PolicyTests`, smoke CI |
| Identité → actions de la passerelle | Une identité obtient une action non accordée | Liste fermée de `KNOWN_ACTIONS` ; action inconnue ou absente de la politique refusée ; création d’identité persiste exactement les actions sélectionnées | **Automatique** — `policy.py`, `control_plane.py`, `PolicyTests` |
| Inventaire MCP amont → autorisation | La simple découverte d’un outil accorde un droit ou une collision de noms mélange deux connecteurs | L’inventaire est uniquement un catalogue administrateur ; une tâche exige au moins un outil d’un connecteur `ready` ; sélection persistée par connecteur+outil+empreinte ; nom virtuel unique dérivé de la tâche et de la sélection | **Automatique/HAOS** — `create_task`, tests de dépendances ; collision de noms déjà exercée en recette. **À compléter** : lancer deux serveurs MCP factices indépendants dans la CI pour fermer explicitement ce gate |
| Tâche/worker → invocation d’une capacité | Appel d’un outil non sélectionné, appel avant réclamation, réutilisation pour un autre travail ou après expiration | Publication limitée aux outils de la tâche ; invocation exige une tentative active appartenant à l’identité et un job `leased` ; résolution exacte par nom virtuel ; connecteur `ready`, activé, empreinte inchangée ; refus `capability_not_available` sinon | **Automatique** — `control_plane.py`, `control_plane_smoke.py`, tests `fixed_arguments_v1`/capability dans `test_foundation.py` |
| Worker → lease de job | Vol de lease, double claim, prolongation indéfinie ou concurrence | Claim transactionnel `BEGIN IMMEDIATE` ; un lease actif par identité ; token de lease vérifié par HMAC ; propriété de l’identité vérifiée ; expiration 5 min avec plafond 30 min ; retries bornés puis dead letter | **Automatique** — `claim_job`, `_leased_attempt`, `control_plane_smoke.py`, tests concurrents |
| Arguments agent → appel MCP amont | Injection d’un argument caché, inconnu ou hors schéma | Validation du schéma virtuel ; `additionalProperties: false` pour `fixed_arguments_v1` ; valeurs fixes injectées côté serveur après validation ; tentative de fournir une propriété cachée refusée ; objet fusionné revalidé contre le schéma amont complet | **Automatique + HAOS** — `fixed_arguments.py`, `json_contracts.py`, tests complets et recette HAOS 0.46.5 |
| Métadonnées/schémas MCP amont → passerelle | Schéma malveillant, contrainte silencieusement ignorée, référence externe ou amplification | JSON Schema Draft 2020-12 fail-closed ; mots-clés/formats admis explicitement ; références externes refusées ; schéma limité à 16 Kio et catalogue à 200 outils ; changement d’empreinte rend la tâche indisponible | **Automatique** — `connectors.py`, `json_contracts.py`, `ConnectorContractTests`, tests de rejet de schéma |
| Résultat/erreur MCP amont → agent/logs | Secret réinjecté/échoé par le serveur amont, résultat surdimensionné ou exception contenant des données sensibles | Résultat limité à 256 Kio ; redaction récursive par noms de clés, tokens et valeurs sensibles transitoires ; exceptions amont normalisées en `upstream_call_failed` sans conserver le traceback potentiellement sensible | **Automatique + HAOS** — `redaction.py`, `mcp_api.py`, tests de redaction, recette HAOS 0.46.3–0.46.5 |
| Configuration admin → endpoint MCP amont | Un agent détourne l’endpoint ou injecte des credentials dans une URL | Endpoint provenant uniquement de la configuration administrateur ; un payload de job/outil ne peut pas le remplacer ; seulement `http`/`https`, hôte requis, pas de userinfo ni fragment, redirections désactivées ; Bearer facultatif ajouté côté passerelle | **Automatique** — `connectors.py`, `ConnectorContractTests`. Le choix volontaire d’une adresse privée/loopback par l’administrateur est autorisé par conception, pas traité comme une escalade client |
| Stockage → secrets connecteur / arguments sensibles | Lecture accidentelle dans UI, audit, rapport ou échec de rotation qui écrase le secret valide | Configuration connecteur et `fixed_sensitive` chiffrés avec Fernet dérivé du pepper ; réponses admin n’exposent que `has_secret` ; endpoint complet/Bearer non réaffichés ; rotation séparée ; échec de rotation conserve l’ancien secret ; redaction avant sortie | **Automatique + HAOS** — `connectors.py`, `fixed_arguments.py`, tests 0.46.6/0.46.7 et recettes HAOS |
| Mutation connecteur → exécution active | Changer endpoint/secret pendant qu’un job dépend du connecteur et créer une course incohérente | Modification de connexion et rotation refusées avec `connector_execution_active` avant discovery/mutation ; refus durablement audité sans endpoint/secret demandé ; simple renommage sans changement de connexion reste permis | **Automatique + HAOS** — tests `ConnectorDiscoveryVisibilityTests`, recette 0.46.7 avec chaîne de 23 entrées valide |
| Source d’événements / planificateur → tâche | Une source choisit arbitrairement la tâche exécutée, duplication ou tempête | Mapping lie identité source + type d’événement + tâche ; la requête d’événement ne choisit pas la tâche ; idempotence, rate limit, cooldown, queue bornée, incidents atomiques et retries bornés ; planifications référencent une tâche prête | **Automatique + HAOS** — `control_plane.py`, `control_plane_smoke.py`, tests d’incidents/concurrence, recette Home Assistant réelle |
| Audit → détection d’altération | Suppression/modification d’entrées ou rollback silencieux d’un refus | Entrées append-oriented chaînées par HMAC ; vérification complète et incrémentale avec revalidation de l’ancre ; incohérence déclenche un full check et ne remplace pas le dernier checkpoint valide ; refus critiques committés avant retour d’erreur | **Automatique + HAOS** — tests `AuditVerificationCheckpointTests`, tests de denied audit, vérifications HAOS 0.46.5/0.46.7 |
| Processus App → hôte HAOS | Compromission de l’App puis exécution/fichiers/capabilities trop larges | Listeners UID 1000 ; App non privilégiée, sans host network ; AppArmor enforce ; seules capabilities `chown`, `kill`, `setgid`, `setuid` ; exécutables et écritures persistantes explicitement bornés ; réseau TCP inet/inet6 uniquement | **Automatique + HAOS** — `apparmor.txt`, `run.sh`, `config.yaml`, `scripts/validate.py`, trace d’exécutables CI et campagne AppArmor HAOS acceptée |
| Réseau opérateur → port 8098 | Exposition Internet d’un bearer endpoint ou interception sur HTTP | Port non publié par défaut ; documentation limite l’usage direct à un LAN/VPN de confiance ; HTTPS peut être utilisé pour un connecteur amont mais Agent Gateway n’est pas un terminateur TLS public | **Documenté** — `config.yaml`, README FR/EN, `MCP_COMPATIBILITY.md` |

### Invariants d’autorisation vérifiés

Les propriétés suivantes doivent rester vraies à chaque release :

1. **Aucune capacité par découverte seule.** Un inventaire MCP ne modifie jamais
   les droits d’un client.
2. **Sélection exacte.** Seuls les outils persistés dans la révision de tâche
   associée au job peuvent être publiés et résolus.
3. **Contexte d’exécution obligatoire.** Une capacité éventuellement annoncée
   avant claim reste non invocable tant que l’identité ne possède pas le lease
   actif correspondant.
4. **Fail closed sur dépendance.** Connecteur désactivé/non prêt, outil absent ou
   empreinte modifiée bloquent l’exécution au lieu de dégrader silencieusement
   le contrat.
5. **Arguments bornés.** Le mode standard applique le schéma amont admis ;
   `fixed_arguments_v1` réduit encore la surface et ne peut jamais l’élargir.
6. **Pas de classification read/write comme autorisation.** La sélection
   explicite de l’administrateur est la décision d’autorisation ; les contrôles
   vérifient ensuite que l’appel reste exactement dans cette enveloppe.

### Risques résiduels et hypothèses de confiance

- **L’administrateur Home Assistant est une autorité de confiance.** Un compte
  administrateur compromis peut volontairement configurer un connecteur et une
  tâche puissants. Agent Gateway vise à appliquer cette configuration exactement,
  pas à contester l’intention de l’administrateur.
- **Un serveur MCP amont est non fiable quant à ses données**, mais il possède
  nécessairement les pouvoirs de ses propres outils. Agent Gateway limite ce que
  l’agent peut demander ; il ne peut pas garantir que l’implémentation amont d’un
  outil respecte sa description.
- **Un Bearer volé reste utilisable jusqu’à révocation.** La confidentialité du
  transport direct sur le réseau relève du LAN/VPN/TLS déployé par l’opérateur.
- **L’audit est tamper-evident, pas un journal WORM externe.** Un attaquant ayant
  compromis à la fois les données persistantes et le secret cryptographique de
  l’App sort du modèle de détection fourni par la chaîne locale.
- **AppArmor réduit l’impact d’une compromission de processus**, mais ne remplace
  pas la sécurité du noyau, du runtime de conteneur ou de Home Assistant OS.
- La haute disponibilité multi-instance, l’exposition Internet directe et un
  rôle d’authorization server OAuth restent hors périmètre de cette release.

### Gate encore ouvert

La matrice elle-même est maintenant documentée. Le seul élément de preuve
explicitement identifié ici comme encore ouvert est le gate du plan demandant
**deux serveurs MCP factices indépendants exposant un nom d’outil identique dans
un test reproductible**. Le dépôt possède déjà le fixture
`scripts/fake_mcp_server.py` et la collision a été acceptée en recette ; la
prochaine étape consiste à rendre cette preuve automatique et indépendante dans
la CI, sans modifier le modèle d’autorisation.

## English

### Scope and authorization principle

Agent Gateway is a generic application firewall for MCP. Its security model is
**deny by default**: explicit administrator configuration is the authorization
decision. Tool discovery grants no right. A tool becomes usable only after it is
selected in a valid task revision, and only inside the exact envelope formed by
the task, connector, tool, schema fingerprint, calling identity, active lease,
effective schema, and optional `fixed_arguments_v1` restrictions.

Semantic labels such as `read`, `write`, `admin`, `safe`, or `dangerous` are
**not** authorization classes. A state-changing upstream tool explicitly
selected by the administrator is governed by the same controls as a read tool.
Agent Gateway does not add a second transactional approval or risk engine that
would override that administrator decision.

This document records implemented trust boundaries. **Automated** evidence is
exercised by Python tests or CI; **HAOS** denotes an already executed manual
acceptance on the real App; **To complete** marks a release gate that still needs
an explicit reproducible proof.

### Boundary matrix

| Boundary | Threat | Enforced control | Current evidence |
| --- | --- | --- | --- |
| Clean install → capabilities | An implicit connector, vendor, task domain, or powerful tool is enabled by default | Fresh schema creates no connector/task/identity; port `8098` is unpublished by default; no HA-MCP/Gatus connector is fixed in App configuration | **Automated** — `database.py`, `config.yaml`, `scripts/validate.py`, CI smoke asserts zero connectors/tasks |
| Administrator browser → admin listener | Direct admin API access, Ingress bypass, or forged mutation | Separate admin listener; expected Ingress proxy IP and `X-Ingress-Path` required; mutations require matching CSRF cookie/header; CSP, `no-store`, `nosniff`, `no-referrer` | **Automated** — `main.py`, `http_api.py`, `surfaces.py`, surface tests and CI smoke |
| Network client → public MCP/event surface | Missing, malformed, forged, or revoked credential; gateway-action escalation | Opaque Bearer; plaintext secret not retained, HMAC verifier with pepper; credential revocation; explicit deny-by-default actions; no admin routes on public listener | **Automated** — `security.py`, `policy.py`, `mcp_api.py`, `surfaces.py`, credential/policy tests and CI smoke |
| Identity → gateway actions | Identity receives an action it was not granted | Closed `KNOWN_ACTIONS`; unknown or absent actions denied; identity creation persists exactly selected actions | **Automated** — `policy.py`, `control_plane.py`, `PolicyTests` |
| Upstream inventory → authorization | Discovery grants capability or duplicate tool names collide across connectors | Inventory is administrative metadata only; task requires a selected tool from a ready connector; selection persists connector+tool+fingerprint; virtual name is unique to task/selection | **Automated/HAOS** — task dependency tests and accepted duplicate-name recipe. **To complete**: run two independent fake MCP servers in CI |
| Task/worker → capability invocation | Invoke unselected tool, invoke before claim, reuse for another job, or invoke after expiry | Only task tools are advertised; resolution requires an identity-owned active lease and leased job; exact virtual name; enabled/ready connector; unchanged fingerprint; otherwise `capability_not_available` | **Automated** — `control_plane.py`, `control_plane_smoke.py`, capability/fixed-argument tests |
| Worker → job lease | Lease theft, double claim, unbounded extension, race | Transactional claim; one active lease per identity; HMAC lease token; identity ownership check; 5-minute lease capped at 30 minutes; bounded retry/dead-letter | **Automated** — `claim_job`, `_leased_attempt`, `control_plane_smoke.py`, concurrency tests |
| Agent arguments → upstream call | Hidden/unknown/out-of-schema argument injection | Effective-schema validation; `additionalProperties: false` for fixed mode; server-side fixed-value injection; hidden property submission rejected; merged call revalidated against full admitted upstream schema | **Automated + HAOS** — `fixed_arguments.py`, `json_contracts.py`, complete tests and 0.46.5 HAOS acceptance |
| Upstream schema/metadata → gateway | Malicious schema, silently ignored constraint, external reference, amplification | Fail-closed Draft 2020-12 profile; explicit keywords/formats; external references rejected; 16 KiB schema and 200-tool limits; fingerprint drift makes tasks unavailable | **Automated** — `connectors.py`, `json_contracts.py`, connector/schema rejection tests |
| Upstream result/error → agent/logs | Secret echoed by upstream, oversized result, sensitive exception text | 256 KiB result limit; recursive key/token/transient-value redaction; upstream exception normalized to `upstream_call_failed` without retaining possibly sensitive traceback | **Automated + HAOS** — `redaction.py`, `mcp_api.py`, redaction tests and 0.46.3–0.46.5 HAOS recipes |
| Admin configuration → upstream endpoint | Agent overrides endpoint or injects URL credentials | Endpoint comes only from administrator configuration and cannot be overridden by job/tool input; `http`/`https` only, host required, no userinfo/fragment, redirects disabled; optional Bearer added inside gateway | **Automated** — `connectors.py`, `ConnectorContractTests`. Administrator-selected private/loopback endpoints are intentionally allowed |
| Persistent storage → connector/fixed secrets | Accidental disclosure in UI/audit/report or failed rotation replaces working secret | Connector config and sensitive fixed args encrypted with Fernet derived from pepper; admin response exposes `has_secret` only; full endpoint/Bearer not redisplayed; explicit rotation; failed rotation preserves old secret; redaction before output | **Automated + HAOS** — connector/fixed-argument code, 0.46.6/0.46.7 tests and HAOS recipes |
| Connector mutation → active execution | Endpoint/secret changes race with a dependent running job | Connection mutation and secret rotation rejected with `connector_execution_active` before discovery/mutation; durable denial contains no requested endpoint/secret; display-name-only rename remains allowed | **Automated + HAOS** — connector mutation tests and 0.46.7 HAOS acceptance |
| Event source/scheduler → task | Source chooses arbitrary task, replay, storm, or duplicate work | Mapping binds exact source identity + event type + task; event payload cannot choose task; idempotency, rate limit, cooldown, bounded queue, atomic grace incidents and bounded retries; schedules reference ready tasks | **Automated + HAOS** — `control_plane.py`, smoke/concurrency tests and real Home Assistant recipe |
| Audit trail → tamper detection | Silent modification/removal or denial rollback | Append-oriented HMAC chain; full/incremental verification with authenticated-anchor revalidation; inconsistency triggers full traversal without replacing last valid checkpoint; critical denials committed before error return | **Automated + HAOS** — audit checkpoint/denial tests and 0.46.5/0.46.7 HAOS verification |
| App process → HAOS host | Compromised process gains broad execution/files/capabilities | Listener UID 1000; non-privileged App, no host networking; enforcing AppArmor; only `chown`, `kill`, `setgid`, `setuid`; explicit executable and persistent-write allowlists; TCP inet/inet6 only | **Automated + HAOS** — `apparmor.txt`, `run.sh`, `config.yaml`, `scripts/validate.py`, CI executable tracing and accepted HAOS AppArmor campaign |
| Operator network → port 8098 | Internet exposure of Bearer endpoint or cleartext interception | Port unpublished by default; direct use documented for trusted LAN/VPN only; Agent Gateway is not a public TLS terminator | **Documented** — `config.yaml`, bilingual README, `MCP_COMPATIBILITY.md` |

### Authorization invariants

1. **Discovery alone never grants capability.** MCP inventory changes no client
   rights.
2. **Exact selection.** Only tools persisted in the job task revision may be
   advertised and resolved.
3. **Execution context is mandatory.** A capability advertised before claim is
   still not invocable until the identity owns the corresponding active lease.
4. **Dependency drift fails closed.** Disabled/unready connector, missing tool,
   or changed fingerprint blocks execution instead of silently weakening the
   contract.
5. **Arguments are bounded.** Standard mode enforces the admitted upstream
   schema; `fixed_arguments_v1` can only narrow that surface.
6. **Read/write semantics do not authorize.** Explicit administrator selection
   is the authorization decision; enforcement then proves that each call remains
   inside that exact envelope.

### Residual risks and trust assumptions

- **The Home Assistant administrator is trusted authority.** A compromised admin
  account can deliberately configure a powerful connector/task. Agent Gateway's
  responsibility is exact enforcement, not second-guessing admin intent.
- **Upstream MCP servers are untrusted for data**, but necessarily retain the
  power of their own tools. Agent Gateway constrains what the agent may request;
  it cannot prove that an upstream implementation matches its description.
- **A stolen Bearer remains usable until revocation.** Confidentiality of direct
  network transport depends on operator LAN/VPN/TLS deployment.
- **The audit is tamper-evident, not external WORM storage.** An attacker who
  compromises both persistent data and the App cryptographic secret is outside
  the local chain's tamper-detection trust assumption.
- **AppArmor limits process compromise impact** but does not replace kernel,
  container-runtime, or Home Assistant OS security.
- Multi-instance HA, direct Internet exposure, and acting as an OAuth
  authorization server remain outside this release scope.

### Remaining open gate

The matrix itself is now documented. The only evidence item explicitly left
open here is the plan requirement for **two independent fake MCP servers exposing
an overlapping upstream tool name in a reproducible test**. The repository
already contains `scripts/fake_mcp_server.py`, and duplicate-name behavior has
passed acceptance; the next release-gate step is to make that proof independent
and automatic in CI without changing the authorization model.
