# Agent Execution Plane — Implementation Plan

Status: **authoritative implementation sequence — Lots 0 and 1 accepted; Lot 2 next**.

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
- the caller/source supplies objective, input and the exact **model-invocable MCP capability envelope** for the execution;
- AEP never decides which operational capabilities are authorized;
- AEP never derives authorization from a broader `tools/list` inventory;
- when ACP is the source, the claimed job's `allowed_capabilities` is the authoritative model capability envelope;
- ACP lifecycle tools used by AEP itself are never exposed to the reasoning model merely because they are available on the same MCP server;
- ACP owns connector configuration/discovery, task selection, virtual capability construction, effective schemas, restrictions such as `fixed_arguments_v1`, authorization and fail-closed upstream resolution;
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

Status: **accepted on HAOS**.

### Goal

Create the smallest real Agent Execution Plane App that installs, starts and can be operated safely on HAOS before model/execution behavior is added.

### Accepted scope

- HAOS App metadata under `agent_execution_plane/`;
- application version source and `Agent Execution Plane vX.Y.Z` header rendering;
- committed authoritative `icon.png` and `logo.png`;
- Home Assistant base image and reproducible build discipline;
- unprivileged runtime user and startup script;
- SQLite generation-1 infrastructure;
- fixed internal administration listener on `8099` through Ingress;
- fixed internal standalone API listener on `8098`, exposed through a user-configurable HAOS Network host-port mapping;
- non-sensitive `/health/live` and `/health/ready`;
- least-privilege AppArmor foundation validated on real HAOS;
- ACP-style Ingress shell;
- French/English switch;
- light/dark switch;
- Overview and Activity shell;
- CI and container persistence smoke tests.

Acceptance was completed through the 0.1.x line; a full HAOS host reboot was intentionally not required because the App-level restart path supplied the relevant evidence without unnecessarily disrupting the host.

## Lot 1 — configured models and provider adapters

Status: **accepted on HAOS in 0.3.1**.

### Goal

Make Execution Plane able to configure, validate, order and monitor reasoning models without executing source work yet.

### Accepted scope

- generation-1 `models` persistence;
- App-local encryption key under `/data/private`;
- encrypted reversible provider credentials;
- Ingress **Models** view;
- create/edit/delete configured model;
- enabled/disabled state;
- deterministic priority reordering;
- per-model timeout in minutes, default 5, positive values only and no product maximum;
- Ollama-compatible adapter;
- OpenAI-compatible `/v1/chat/completions` adapter;
- official `openai_chatgpt_oauth` adapter through exactly pinned `openai-codex==0.144.4` and `openai-codex-cli-bin==0.144.4` over local stdio JSONL only;
- dedicated restrictive `/data/private/codex-home`, forced ChatGPT login and file-owned Codex credential storage with API-key environment variables removed from the child process;
- shared ChatGPT device-code login/account/logout UI and Codex `model/list` catalogue without OAuth-token handling by AEP;
- validate-before-save creation/edit lifecycle;
- existing configuration preserved when candidate validation fails;
- Ollama model/tool capability validation from native metadata where available;
- bounded explicit tool-call inference probe where generic OpenAI-compatible metadata cannot establish required tool support;
- non-inference startup/health checks only;
- non-inference OAuth validation based only on app-server handshake, ChatGPT account state and catalogue membership;
- bilingual responsive Models UI including final 0.3.1 polish.

Real HAOS acceptance proved Codex app-server execution under AppArmor, device-code OAuth with a ChatGPT subscription, real `model/list`, model persistence across App restart, account persistence, model deletion without logout, explicit logout and non-disclosure in Activity.

## Lot 2 — common execution engine and MCP tool loop

Status: **planned — next implementation lot**.

### Goal

Implement the source-neutral execution engine once, before attaching either public source boundary end to end.

### Architectural rule for this lot

The execution core receives a **source-supplied capability envelope**. It does not create one.

The Lot 2 fake-source harness must therefore provide:

- objective/input;
- MCP endpoint/credential;
- exact model-invocable capability descriptors;
- optional result schema.

The engine may use MCP `tools/list` only to verify that those supplied capabilities still exist with the expected effective schemas. It must not turn the complete MCP inventory into a new authorization decision.

In the later ACP boundary, the exact envelope will come from `jobs_claim_v1.job.allowed_capabilities`. ACP lifecycle tools on the same MCP server remain source-boundary mechanics and are not model tools.

### Scope

- internal `ExecutionRequest` / `ExecutionOutcome` values only;
- one atomic global execution slot;
- deterministic source objective/input serialization without business enrichment;
- deterministic application of enabled compatible models by administrator priority;
- entire-attempt per-model timeout;
- provider conversation/tool-call normalization;
- one Streamable HTTP MCP session per execution;
- paginated `tools/list` support used solely for source-envelope consistency verification;
- exact verification that every source-supplied capability exists with the expected effective input schema;
- no addition of tools absent from the source envelope;
- no semantic narrowing or classification of the source envelope by AEP;
- local argument validation against the frozen source-supplied schema before `tools/call`;
- optional deterministic one-to-one provider transport aliasing only when provider naming constraints require it;
- `mcp_effect_possible` set at dispatch time;
- no fallback after dispatch;
- provider/model fallback only for qualifying pre-MCP technical failure;
- fallback restarts from original source material and original capability envelope with no prior model state;
- caller-provided optional result schema;
- provider structured-output mapping;
- local JSON-schema validation;
- output-contract failure/fallback behavior;
- technical payload/tool-count bounds from `TECHNICAL_DESIGN.md`;
- no reasoning/conversation persistence;
- `In use` model locking required by the already accepted model contract.

### Provider behavior

#### Ollama-compatible

Implement the model/tool loop behind the provider adapter with exactly the frozen source capability envelope.

#### OpenAI-compatible

Implement `/v1/chat/completions` tool calls/results and structured output as supported, again using exactly the frozen source envelope.

#### OpenAI ChatGPT OAuth

Before relying on Codex execution, CI must prove with the real pinned 0.144.4 runtime that AEP can use ephemeral `thread/start`/`turn/start` plus `dynamicTools` without exposing any native Codex capability or unrelated instruction source.

The OAuth execution wrapper must:

- use an execution-specific strict method allow-list separate from the Lot 1 account/catalogue wrapper;
- never auto-approve command/file/permission requests;
- never use native Codex shell, filesystem, apply-patch, web, image, MCP, skills, plugins/apps/connectors, sub-agents or collaboration tools;
- use `ephemeral: true`;
- use `environments: []`;
- select no capability root/workspace;
- require empty `instructionSources`;
- map only the frozen source capability envelope into `dynamicTools`;
- route `item/tool/call` back through AEP's MCP loop;
- use the official output-schema mechanism when applicable rather than semantic prompt enrichment.

If exact isolation cannot be demonstrated, `openai_chatgpt_oauth` is execution-incompatible. Do not weaken the MCP-only invariant and do not fall back to an OpenAI Platform API key.

### Explicit anti-goals

Do not implement:

- ACP connection configuration;
- ACP polling/claim/heartbeat/result delivery;
- ACP identities, connectors, task definitions, capability selection or authorization logic;
- ACP virtual capability construction or `fixed_arguments_v1`;
- standalone HTTP execution lifecycle;
- standalone Bearer management;
- persistent active/pending execution lifecycle;
- internal queue/scheduler;
- manual execution UI;
- MCP connector catalogue;
- capability/authorization editor;
- output-quality/business judgment;
- repair-agent loop;
- Bridge behavior, SSH, browser or vendor HTTP.

### CI evidence

#### Engine and model ordering

- one global slot;
- concurrent second execution => busy;
- no queue;
- configured priority order respected;
- disabled model ignored;
- model1 qualifying pre-MCP technical failure -> model2 succeeds;
- next execution starts from model1 again;
- no automatic priority/enabled mutation;
- active model delete/disable/technical edit refused while priority change remains allowed for later executions.

#### Source capability envelope

Use a fake MCP server that deliberately exposes more than the fake source envelope, including lifecycle-like/unrelated tools.

Prove:

- empty source envelope -> zero model-visible tools even when MCP `tools/list` is non-empty;
- N source capabilities -> exactly those N reach the provider/model;
- unrelated MCP inventory entries never become model-visible;
- no AEP rule chooses a different semantic subset;
- paginated `tools/list` still validates source capabilities correctly;
- missing source capability fails closed;
- effective-schema mismatch fails closed;
- >128 source capabilities fails rather than selecting/truncating a subset;
- `tools/list_changed` never adds a capability mid-execution;
- provider transport aliasing, if required, is deterministic one-to-one, reversible and collision-safe.

#### Tool dispatch

- model request outside frozen source envelope => no dispatch;
- invalid JSON/schema => no dispatch;
- valid call => exactly one dispatch;
- argument and dispatch-count bounds;
- result bounds;
- no semantic authorization logic in AEP.

#### Side effect / fallback

- provider failure before dispatch -> fallback allowed;
- provider failure after dispatch -> no fallback;
- MCP request dispatched but response lost -> no fallback;
- MCP tool error -> no fallback;
- timeout before dispatch -> fallback;
- timeout after dispatch -> no fallback.

#### Results

- free-form result success;
- structured result success/failure;
- schema invalid before MCP -> fallback possible;
- schema invalid after MCP -> no fallback;
- limit overflow fails rather than silently truncating.

#### Complete timeout

- one monotonic deadline covers the complete model attempt, including provider turns and MCP exchanges;
- deadline does not reset per turn/tool;
- a fallback model receives its own configured full timeout.

#### Pinned OAuth isolation — blocking

Using the real Codex 0.144.4 runtime and a deterministic local capture backend, with no real OpenAI account/credential:

- ephemeral thread;
- `environments: []`;
- empty `instructionSources`;
- no workspace/capability root;
- empty source envelope => provider receives zero tools;
- N source tools => provider receives exactly N mapped tools;
- no native Codex capability appears;
- no project/coding instruction source is injected;
- dynamic tool call returns through `item/tool/call` to the fake MCP path;
- unexpected command/file/permission request is never approved;
- no durable thread/session history remains.

The actual outbound provider request must be captured; checking only the AEP `thread/start` payload is insufficient.

### Acceptance

Lot 2 has no public execution source, so real HAOS acceptance is limited to what is meaningful for the new runtime mechanics. Independent review and CI must provide the functional engine evidence, followed by a HAOS deployment/start/runtime smoke sufficient to validate dependencies/AppArmor changes. Lot 2 is accepted only after that evidence is reviewed; CI green alone is not acceptance.

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
- exact request contract for objective/input/MCP endpoint/optional MCP Bearer/**exact caller-selected model capability envelope**/optional result schema;
- caller cannot select model;
- AEP does not derive the standalone capability envelope from `tools/list`;
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
- caller capability envelope remains execution-scoped;
- request/result/body bounds.

### HAOS acceptance

Run a real standalone execution against a configured model and a test MCP server whose inventory contains both requested and unrelated tools. Confirm only the caller-supplied envelope reaches the model, retrieve the result, prove the engine remains blocked before ACK, ACK it, then prove a new execution is accepted. Repeat the pending-result step across an App restart.

Acceptance of this lot proves the independence invariant: Execution Plane is useful with no ACP installed/configured.

## Lot 4 — Agent Control Plane boundary

Status: **planned**.

### Goal

Attach the existing ACP contract to the already-working common execution engine without creating ACP-specific execution semantics or duplicating ACP governance.

### Scope

- Ingress ACP connection configuration: MCP URL + protected worker Bearer credential;
- validate-before-save connection changes;
- ACP connectivity state without making App readiness depend on ACP;
- fixed 1-second idle claim polling while a usable model exists;
- stop claiming when slot is occupied;
- call `jobs_claim_v1` through the ACP boundary;
- map ACP job objective/input/**`allowed_capabilities` exactly**/required report schema into the common execution request;
- treat ACP `allowed_capabilities` as authoritative for model visibility;
- keep ACP lifecycle tools (`jobs_claim_v1`, heartbeat, complete, fail and other boundary operations) out of the model envelope;
- use ACP's MCP `tools/list` only to verify the claimed capability descriptors remain technically present/applicable, never to choose authorized capabilities;
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

No ACP task/trigger/job-history UI, no ACP database access, no connector catalogue, no task/capability editor, no copied ACP connector credentials, no recreated `fixed_arguments_v1`, no duplicated authorization or lease policy, no model selection from ACP, no conversion of ACP's current 30-minute attempt lifetime into an Execution Plane timeout limit.

### CI evidence

Contract tests must use the **current ACP behavior**, including a public MCP surface containing both lifecycle tools and virtual task capabilities.

Prove:

- `jobs_claim_v1.job.allowed_capabilities` becomes exactly the model envelope;
- lifecycle tools remain AEP-boundary-only and never become model-visible;
- virtual capability effective schemas match the claim envelope;
- an ACP `tools/list_changed` event does not broaden the frozen model envelope;
- no connector endpoint, connector credential, hidden/fixed argument or upstream tool name is required by AEP;
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

1. configure a dedicated worker identity with only the ACP actions required by the boundary;
2. connect Execution Plane;
3. create one bounded ACP task/job with known virtual capabilities;
4. observe automatic claim;
5. confirm the model sees exactly the job's `allowed_capabilities` and none of the ACP lifecycle tools;
6. observe model/MCP execution;
7. confirm ACP performs the governed virtual capability resolution/call;
8. confirm ACP receives one result/report;
9. confirm Execution Plane returns to idle and then claims only the next queued job;
10. exercise one ACP outage/recovery scenario without duplicate execution.

This lot is accepted only after the real ACP<->Execution Plane path works on HAOS with the responsibility boundary intact.

## Lot 5 — release hardening and production baseline

Status: **planned**.

### Goal

Close the first public/production-quality Execution Plane release without adding new product behavior.

### Scope

- final AppArmor minimization from recorded executable/runtime evidence;
- graceful shutdown behavior for idle, active and pending-result states;
- complete secret/redaction review;
- final safety-bound review;
- final ACP/AEP responsibility-boundary review against `ARCHITECTURE_CHARTER.md` and the actual ACP contract;
- final bilingual UI copy review;
- responsive Ingress review on desktop/mobile widths;
- final presentation review while preserving the committed authoritative `icon.png` and `logo.png`;
- complete `README.md`, `README.fr.md`, `DOCS.md` and detailed bilingual documentation;
- compatibility statement for Ollama-compatible, OpenAI-compatible, OpenAI ChatGPT OAuth and MCP Streamable HTTP expectations;
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
- validate ACP execution and capability-envelope separation;
- restart App and HAOS with configuration preserved where host reboot evidence is materially required;
- validate pending-result restart behavior;
- validate language/theme/version, authoritative icon/logo presentation and configured Network port;
- verify AppArmor-enforced normal operation and graceful stop/start;
- inspect logs for secret/data leakage and unexpected errors.

When this lot is accepted, that installed version becomes the **Agent Execution Plane production persistence baseline**.

From that point forward, routine App-data deletion/clean reinstall is forbidden as an upgrade strategy. Future persistence changes require explicit, deterministic, tested data-preserving upgrades.

## Post-baseline rule

After Lot 5 acceptance, new functionality is proposed as bounded later lots. The first implementation plan must not grow opportunistically while coding.

If implementation discovers a genuinely missing product choice, work pauses only on the affected point and the choice is presented to the administrator concretely. Pure implementation choices are resolved within the technical design without reopening the functional preparation phase.