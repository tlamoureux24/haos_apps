# Agent Execution Plane — Implementation Plan

Status: **authoritative implementation sequence — implementation not started**.

This plan is derived from `PROJECT_BRIEF.md`, `TECHNICAL_DESIGN.md` and the root `ARCHITECTURE_CHARTER.md`.

The plan is finite. Product behavior is already closed; implementation lots must not reopen it unless real code/HAOS evidence exposes a contradiction that cannot be solved within the validated design.

For every lot:

`planned -> implemented -> independently reviewed -> CI conformant -> deployed on HAOS -> real acceptance tested -> accepted`

Codex implements bounded lots. A Codex summary is not acceptance evidence.

## Global invariants for every lot

The following rules apply from the first commit onward:

- Agent Execution Plane remains a model execution engine, not a control plane;
- ACP and standalone API use the same core execution semantics;
- one global execution slot, no internal waiting queue;
- the caller/source supplies objective, input and exact MCP capability surface;
- the caller never selects the model;
- configured models are tried in administrator priority order;
- 5-minute default timeout per configured model, with no caller-derived product maximum;
- no automatic model fallback after an MCP `tools/call` has been dispatched;
- MCP is the only model-invocable capability path;
- no persistent job/model-conversation history;
- pending results and minimal interruption state are persisted only for safe delivery/recovery;
- no hidden business/system prompt enrichment;
- secrets and reasoning content are never logged;
- the App runs as a normal HAOS App with Ingress, AppArmor, logo/icon and bilingual light/dark administration UI;
- the committed `agent_execution_plane/icon.png` and `agent_execution_plane/logo.png` are the authoritative branding assets and must not be replaced, regenerated or substituted without an explicit later product decision;
- implementation details must stay generic and provider/source-specific mechanics stay at thin boundaries.

## Lot 0 — executable HAOS application shell

Status: **planned**.

### Goal

Create the smallest real Agent Execution Plane App that installs, starts and can be operated safely on HAOS before model/execution behavior is added.

### Scope

- HAOS App metadata under `agent_execution_plane/`;
- application version source and `Agent Execution Plane vX.Y.Z` header rendering;
- preserve the committed root `icon.png` and `logo.png` unchanged as the HAOS App's authoritative icon/logo assets so Home Assistant repository/Supervisor presentation uses those files rather than generated substitutes;
- the Ingress header must visibly render the committed `icon.png` (or an exact packaged copy of the same asset) immediately with the `Agent Execution Plane vX.Y.Z` product identity; `logo.png` may additionally be reused elsewhere in the UI but does not replace this mandatory header icon;
- Dockerfile based on the Home Assistant base image with pinned provenance handling equivalent in discipline to ACP;
- unprivileged runtime user and startup script;
- SQLite initialization plumbing with generation-1 empty schema infrastructure;
- fixed internal administration listener on `8099` through Ingress;
- fixed internal standalone API listener on `8098`, exposed through a user-configurable HAOS Network host-port mapping;
- non-sensitive `/health/live` and `/health/ready`;
- first least-privilege `agent_execution_plane` AppArmor profile based on actual startup/runtime requirements;
- Ingress shell using ACP's visual language;
- French/English switch;
- light/dark switch;
- Overview shell showing App/engine readiness without pretending external models/ACP are configured;
- basic English/French installation documentation;
- dedicated GitHub Actions validation workflow;
- container smoke test proving listener isolation and persistent `/data` across restart.

### Explicit anti-goals

Do not implement model providers, ACP polling, standalone execution submission, MCP tool execution, task/job storage or fake placeholder business behavior.

### CI evidence

- metadata/source validation;
- committed `icon.png` and `logo.png` are present in the packaged App unchanged and the Ingress header resolves/renders the authoritative `icon.png` asset rather than an emoji, generated icon or unrelated substitute;
- Python compile/tests;
- amd64 image build;
- startup and both health endpoints;
- Ingress-prefix correctness;
- bilingual/theme/version/icon UI assertions;
- restart/persistence smoke test;
- initial AppArmor executable inventory.

### HAOS acceptance

1. install the App from the repository and confirm Home Assistant presents the committed App icon/logo correctly;
2. confirm clean startup/logs;
3. open Ingress and confirm the committed icon is visible with the product name + version in the header;
4. verify FR/EN;
5. verify light/dark;
6. verify the standalone API host port can be changed in the App Network configuration;
7. restart App and HAOS once, confirming clean recovery and unchanged branding assets.

Acceptance of Lot 0 proves only the App shell/security foundation.

## Lot 1 — configured models and provider adapters

Status: **planned**.

### Goal

Make Execution Plane able to configure, validate, order and monitor reasoning models without executing source work yet.

### Scope

- generation-1 `models` persistence;
- App-local encryption key under `/data/private`;
- encrypted reversible provider credentials;
- Ingress **Models** view;
- create/edit/delete configured model;
- enabled/disabled state;
- drag/buttons or equivalent deterministic priority reordering;
- per-model timeout in minutes, default 5, positive values only and no product maximum;
- Ollama-compatible adapter;
- OpenAI-compatible `/v1/chat/completions` adapter;
- optional provider Bearer/API credential;
- validate-before-save creation/edit lifecycle;
- existing configuration preserved when candidate validation fails;
- Ollama model/tool capability validation from native metadata where available;
- bounded explicit tool-call inference probe where generic OpenAI-compatible metadata cannot establish required tool support;
- visible warning that explicit compatibility validation can consume provider usage;
- non-inference startup/health checks only;
- `Available`, `Unavailable`, `Incompatible`, `Unverified`, `Disabled`, and `In use` UI states as applicable;
- priority changes allowed during use at data-model level, while destructive/technical edits are lockable once engine use exists in later lots.

### Explicit anti-goals

No source job execution, no MCP call loop, no autonomous provider quarantine/reordering, no automatic inference-based health polling.

### CI evidence

- fake Ollama-compatible endpoint tests;
- fake OpenAI-compatible endpoint tests;
- tool-call compatibility probe tests;
- candidate-edit rollback tests;
- encrypted-secret/non-disclosure tests;
- timeout and priority tests;
- startup health behavior with unreachable providers.

### HAOS acceptance

Configure at least one reachable compatible model, exercise successful and failed edits, restart the App and confirm model configuration/priority/timeout survive correctly with no secret disclosure.

## Lot 2 — common execution engine and MCP tool loop

Status: **planned**.

### Goal

Implement the source-neutral execution engine once, before attaching either public source boundary end to end.

### Scope

- internal `ExecutionRequest` / `ExecutionOutcome` values only;
- one atomic global execution slot;
- deterministic source objective/input serialization without business enrichment;
- selection of enabled compatible models by administrator priority;
- entire-attempt per-model timeout;
- provider conversation/tool-call normalization;
- one Streamable HTTP MCP session per execution;
- paginated `tools/list` support;
- exact source-supplied tool subset verification;
- fail closed on missing/schema-changed capability;
- local argument validation before `tools/call`;
- `mcp_effect_possible` set at dispatch time;
- no fallback after dispatch;
- provider/model fallback only for qualifying pre-MCP technical failure;
- fallback restarts from original source material with no prior model state;
- caller-provided optional result schema;
- provider structured-output mapping;
- local JSON-schema validation;
- output-contract failure/fallback behavior;
- technical payload/tool-count bounds from `TECHNICAL_DESIGN.md`;
- no reasoning/conversation persistence.

### Explicit anti-goals

No ACP-specific lease semantics in the engine core, no standalone HTTP lifecycle yet, no internal queue, no output-quality/business judgment, no repair-agent loop.

### CI evidence

- model1 fail/model2 succeed before MCP;
- model1 fail after MCP dispatch with no model2 replay;
- MCP request dispatched but response lost still blocks fallback;
- unknown/unlisted tool rejected before dispatch;
- schema drift rejected;
- invalid arguments rejected locally;
- MCP tool failure reported without provider fallback;
- free-form result success;
- structured result success/failure;
- configured timeout covers complete multi-turn attempt;
- limits fail rather than silently truncate.

### Acceptance

This lot can be accepted primarily through independent review and CI because no public source boundary exists yet. A container smoke harness should still exercise a complete fake-source -> model -> fake-MCP -> result path.

## Lot 3 — standalone API, authentication and durable result lifecycle

Status: **planned**.

### Goal

Make Agent Execution Plane fully useful independently of Agent Control Plane.

### Scope

- standalone opaque Bearer credential create/rotate/revoke in Ingress;
- one-way credential verifier storage;
- `POST /api/v1/execute`;
- `GET /api/v1/executions/{id}`;
- `POST /api/v1/executions/{id}/ack`;
- exact request contract for objective/input/MCP endpoint/optional MCP Bearer/exact tools/optional result schema;
- caller cannot select model;
- immediate busy refusal, no queue;
- execution-scoped MCP credentials never promoted to persistent configuration;
- minimal `active_execution` persistence;
- one `pending_result` maximum;
- result persisted before becoming externally available;
- `GET` does not release result;
- `ack` deletes result and frees engine;
- current standalone execution status in Overview;
- confirmed **Abandon pending result** UI action;
- restart while active becomes a factual interrupted pending result, never a replay;
- restart while pending preserves exact result and blocked state;
- complete standalone API documentation in English and French, with copy/paste examples.

### CI evidence

- auth success/failure/rotation/revocation;
- no credential leakage in API/logs;
- accepted submit and opaque ID;
- busy conflict during active execution;
- busy conflict while pending result exists;
- GET repeated without release;
- ACK releases slot exactly once;
- manual abandonment releases slot without rerun;
- active crash/restart -> interrupted result;
- pending crash/restart -> same result;
- caller MCP Bearer never persists after execution;
- request/result/body bounds.

### HAOS acceptance

Run a real standalone execution against a configured model and a test MCP server, retrieve the result, prove the engine remains blocked before ACK, ACK it, then prove a new execution is accepted. Repeat the pending-result step across an App restart.

Acceptance of this lot proves the independence invariant: Execution Plane is useful with no ACP installed/configured.

## Lot 4 — Agent Control Plane boundary

Status: **planned**.

### Goal

Attach the existing ACP contract to the already-working common execution engine without creating ACP-specific execution semantics.

### Scope

- Ingress ACP connection configuration: MCP URL + protected worker Bearer credential;
- validate-before-save connection changes;
- ACP connectivity state without making App readiness depend on ACP;
- fixed 1-second idle claim polling while a usable model exists;
- stop claiming when slot is occupied;
- map `jobs_claim_v1` directly into the common execution request;
- use ACP supplied objective/input/allowed capability surface/required report schema;
- lease token protection and heartbeat;
- continue across one transient heartbeat failure only while current lease remains indisputably valid;
- stop model/no new MCP dispatch when lease validity can no longer be guaranteed;
- jobs complete/fail delivery using ACP's existing contract;
- pending result persisted before ACP delivery;
- same-result delivery retry every second, never rerun model;
- ACP pending delivery state visible in Overview;
- definitive unresolvable delivery refusal remains visible for manual abandonment;
- restart with active ACP execution: no replay, reconcile/report interruption before claiming new work;
- restart with pending ACP result: resume delivery of exact result;
- complete ACP integration documentation in English and French.

### Explicit anti-goals

No ACP task/trigger/job-history UI, no ACP database access, no duplicated lease policy, no model selection from ACP, no conversion of ACP's current 30-minute attempt lifetime into an Execution Plane timeout limit.

### CI evidence

- contract tests against current ACP job tools and capability envelope;
- idle 1-second polling;
- no claim with zero enabled compatible models;
- no second claim while active/pending;
- heartbeat success/transient failure/expiry boundary;
- no MCP dispatch after lease validity is lost;
- completion delivery retry without rerun;
- restart interruption reconciliation;
- ACP unavailable does not make App watchdog-unready;
- ACP and standalone requests cannot own the single slot concurrently.

### HAOS acceptance

Use the real installed Agent Control Plane:

1. configure a dedicated worker identity;
2. connect Execution Plane;
3. create one bounded ACP task/job;
4. observe automatic claim;
5. observe model/MCP execution;
6. confirm ACP receives one result/report;
7. confirm Execution Plane returns to idle and then claims only the next queued job;
8. exercise one ACP outage/recovery scenario without duplicate execution.

This lot is accepted only after the real ACP<->Execution Plane path works on HAOS.

## Lot 5 — release hardening and production baseline

Status: **planned**.

### Goal

Close the first public/production-quality Execution Plane release without adding new product behavior.

### Scope

- final AppArmor minimization from recorded executable/runtime evidence;
- graceful shutdown behavior for idle, active and pending-result states;
- complete secret/redaction review;
- final safety-bound review;
- final bilingual UI copy review;
- responsive Ingress review on desktop/mobile widths;
- final presentation review while preserving the committed authoritative `icon.png` and `logo.png`; replacing either asset requires an explicit later product decision;
- complete `README.md`, `README.fr.md`, `DOCS.md` and French-equivalent detailed documentation;
- compatibility statement for Ollama-compatible, OpenAI-compatible and MCP Streamable HTTP expectations;
- threat/security boundary document focused on Execution Plane;
- final CI workflow including AppArmor trace/inventory, restart, fake-provider/MCP integration and UI smoke tests;
- fresh-install HAOS recipe;
- upgrade/restart recipe preserving configured models/settings;
- no warnings/errors in normal logs;
- update implementation plan with exact accepted version/commit/CI/HAOS evidence.

### HAOS acceptance

Perform the complete real recipe:

- clean install of the release candidate;
- configure models;
- validate standalone execution + ACK;
- validate ACP execution;
- restart App and HAOS with configuration preserved;
- validate pending-result restart behavior;
- validate language/theme/version, authoritative icon/logo presentation and configured Network port;
- verify AppArmor-enforced normal operation and graceful stop/start;
- inspect logs for secret/data leakage and unexpected errors.

When this lot is accepted, that installed version becomes the **Agent Execution Plane production persistence baseline**.

From that point forward, routine App-data deletion/clean reinstall is forbidden as an upgrade strategy. Future persistence changes require explicit, deterministic, tested data-preserving upgrades.

## Post-baseline rule

After Lot 5 acceptance, new functionality is proposed as bounded later lots. The first implementation plan must not grow opportunistically while coding.

If implementation discovers a genuinely missing product choice, work pauses only on the affected point and the choice is presented to the administrator concretely. Pure implementation choices are resolved within the technical design without reopening the functional preparation phase.