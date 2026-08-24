# Agent Execution Plane — Implementation Plan

Status: **authoritative implementation sequence — Lots 0 through 4 accepted on real HAOS**.

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
- the caller/source supplies objective, input and the exact **model-invocable MCP operational capability envelope** for the execution;
- AEP never decides which operational MCP capabilities are authorized;
- AEP never derives authorization from a broader MCP `tools/list` inventory;
- when ACP is the source, the claimed job's `allowed_capabilities` is the authoritative MCP operational capability envelope;
- ACP lifecycle tools used by AEP itself are never exposed to the reasoning model merely because they are available on the same MCP server;
- ACP owns connector configuration/discovery, task selection, virtual capability construction, effective schemas, restrictions such as `fixed_arguments_v1`, authorization and fail-closed upstream resolution;
- the caller never selects the model;
- configured models are tried in administrator priority order;
- 5-minute default timeout per configured model, with no caller-derived product maximum;
- no automatic model fallback after an MCP `tools/call` has been dispatched;
- MCP is the only model-initiated path for **operational access to or actions on user-controlled infrastructure/non-provider technical systems**;
- provider-native reasoning/information helpers such as internal planning or public Web search may be used when they remain inside the provider/runtime responsibility and cannot bypass MCP/ACP to reach user infrastructure, AEP private host state, connector credentials or an alternate connector path;
- provider-native helper presence must never be confused with source authorization of MCP operational capabilities;
- no persistent job/model-conversation history;
- pending results and minimal interruption state are persisted only for safe delivery/recovery;
- no hidden business/system prompt enrichment by AEP;
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

Status: **accepted on HAOS in 0.4.2**.

### Goal

Implement the source-neutral execution engine once, before attaching either public source boundary end to end.

### Architectural rule for this lot

The execution core receives a **source-supplied MCP operational capability envelope**. It does not create one.

The Lot 2 fake-source harness must therefore provide:

- objective/input;
- MCP endpoint/credential;
- exact model-invocable MCP operational capability descriptors;
- optional result schema.

The engine may use MCP `tools/list` only to verify that those supplied capabilities still exist with the expected effective schemas. It must not turn the complete MCP inventory into a new authorization decision.

Provider-native reasoning/information helpers are a separate provider concern. They do not belong to the source MCP envelope and do not grant operational authority. Their presence is acceptable only while they remain non-operational with respect to user infrastructure/AEP private state.

In the later ACP boundary, the exact MCP envelope will come from `jobs_claim_v1.job.allowed_capabilities`. ACP lifecycle tools on the same MCP server remain source-boundary mechanics and are not model tools.

### Scope

- internal `ExecutionRequest` / `ExecutionOutcome` values only;
- one atomic global execution slot;
- deterministic source objective/input serialization without business enrichment;
- deterministic application of enabled compatible models by administrator priority;
- entire-attempt per-model timeout;
- provider conversation/tool-call normalization;
- provider-native reasoning/information helper handling behind provider adapters without creating operational side channels;
- one Streamable HTTP MCP session per execution;
- paginated `tools/list` support used solely for source-envelope consistency verification;
- exact verification that every source-supplied MCP capability exists with the expected effective input schema;
- no addition of MCP tools absent from the source envelope;
- no semantic narrowing or classification of the source MCP envelope by AEP;
- local argument validation against the frozen source-supplied MCP schema before `tools/call`;
- optional deterministic one-to-one provider transport aliasing only when provider naming constraints require it;
- `mcp_effect_possible` set at MCP dispatch time;
- no fallback after MCP dispatch;
- provider/model fallback only for qualifying pre-MCP technical failure;
- permitted provider-native reasoning/information helper use does not by itself cross the MCP side-effect boundary;
- fallback restarts from original source material and original MCP capability envelope with no prior model state;
- caller-provided optional result schema;
- provider structured-output mapping;
- local JSON-schema validation;
- output-contract failure/fallback behavior;
- technical payload/tool-count bounds from `TECHNICAL_DESIGN.md`;
- no reasoning/conversation persistence;
- `In use` model locking required by the already accepted model contract.

### Provider behavior

#### Ollama-compatible

Implement the model/tool loop behind the provider adapter with exactly the frozen source MCP operational capability envelope.

#### OpenAI-compatible

Implement `/v1/chat/completions` tool calls/results and structured output as supported, again using exactly the frozen source MCP envelope.

#### OpenAI ChatGPT OAuth

Use the real pinned Codex 0.144.4 runtime and its normal provider-native reasoning mechanics, but preserve a strict separation between:

1. **AEP-supplied MCP operational tools**, which must correspond exactly to the frozen source MCP envelope; and
2. **Codex-native reasoning/information helpers**, which may exist independently but must not create a path to operate user infrastructure, access AEP private host/filesystem state, obtain connector credentials or invoke an alternate MCP/connector route.

A preflight performed on **2026-08-20** with the real pinned runtime and a deterministic local capture backend established that:

- the AEP dynamic tool is transmitted correctly;
- `ephemeral: true` is respected;
- `instructionSources: []` is respected;
- Codex 0.144.4 additionally injects `update_plan`, `request_user_input`, `view_image` and `web_search`;
- generic permission instructions and five system skills are present;
- `environment_context` contains shell/filesystem/workspace metadata;
- `runtimeWorkspaceRoots` contains the dedicated `CODEX_HOME` root.

These observations **do not constitute a Lot 2 failure by themselves**. They invalidate only the former assumption that the provider request must contain zero native tools.

The OAuth execution wrapper/gate must now prove the actual operational boundary:

- use an execution-specific strict method allow-list separate from the Lot 1 account/catalogue wrapper;
- use `ephemeral: true`;
- use `environments: []`;
- request empty `instructionSources` and do not supply any user project/workspace/AGENTS source;
- map exactly the frozen source MCP envelope into `dynamicTools`;
- route AEP dynamic `item/tool/call` requests back through AEP's MCP loop;
- never auto-approve command/file/permission requests;
- prove `update_plan` is internal planning only;
- allow `web_search` as a provider-native public-information/research helper when it cannot act as an arbitrary private/local-network/vendor-control transport and AEP does not inject private credentials into it;
- ensure `request_user_input` cannot create an unbounded unattended wait; reject/resolve it boundedly when the source has no interactive user channel;
- prove `view_image` cannot read arbitrary AEP host files, `/data/private`, Codex OAuth credential files or other local secrets; otherwise disable/refuse that capability or declare OAuth execution incompatible;
- prove shell/filesystem/workspace metadata does not imply actual local shell/filesystem authority and that no such server request is approved;
- allow generic system skills/runtime instructions only if they do not expose user/project private content, OAuth credential contents, a new business objective or operational authority;
- never use native Codex MCP, plugins/apps/connectors, browser control against user infrastructure, sub-agents or collaboration as an operational side channel;
- use the official output-schema mechanism when applicable rather than semantic prompt enrichment;
- preserve ephemeral execution/no AEP reasoning-history persistence.

If any Codex-native facility provides an unavoidable operational or private-host side channel that AEP cannot disable, refuse or confine, `openai_chatgpt_oauth` is execution-incompatible. Do not weaken the source-authorized MCP operational boundary and do not fall back to an OpenAI Platform API key.

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
- Bridge behavior, SSH, local shell/filesystem, browser control of user infrastructure or vendor HTTP side channels.

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

#### Source MCP capability envelope

Use a fake MCP server that deliberately exposes more than the fake source envelope, including lifecycle-like/unrelated tools.

Prove:

- empty source MCP envelope -> zero **AEP-supplied MCP operational tools** even when MCP `tools/list` is non-empty; provider-native reasoning/information helpers may still exist independently;
- N source MCP capabilities -> exactly those N reach the provider/model as AEP-supplied MCP operational tools;
- unrelated MCP inventory entries never become model-visible as MCP tools;
- no AEP rule chooses a different semantic subset;
- paginated `tools/list` still validates source MCP capabilities correctly;
- missing source MCP capability fails closed;
- effective-schema mismatch fails closed;
- >128 source MCP capabilities fails rather than selecting/truncating a subset;
- `tools/list_changed` never adds an MCP capability mid-execution;
- provider transport aliasing, if required, is deterministic one-to-one, reversible and collision-safe.

#### Tool dispatch

- model request for an AEP/MCP tool outside frozen source envelope => no MCP dispatch;
- invalid JSON/schema => no MCP dispatch;
- valid AEP/MCP call => exactly one MCP dispatch;
- argument and dispatch-count bounds;
- result bounds;
- no semantic authorization logic in AEP;
- permitted provider-native helper activity never becomes an implicit MCP dispatch or operational authorization.

#### Side effect / fallback

- provider failure before MCP dispatch -> fallback allowed;
- permitted provider-native planning/public-information helper use before MCP dispatch does not by itself block fallback;
- provider failure after MCP dispatch -> no fallback;
- MCP request dispatched but response lost -> no fallback;
- MCP tool error -> no fallback;
- timeout before MCP dispatch -> fallback;
- timeout after MCP dispatch -> no fallback.

#### Results

- free-form result success;
- structured result success/failure;
- schema invalid before MCP -> fallback possible;
- schema invalid after MCP -> no fallback;
- limit overflow fails rather than silently truncating.

#### Complete timeout

- one monotonic deadline covers the complete model attempt, including provider turns, permitted provider-native helper activity and MCP exchanges;
- deadline does not reset per turn/tool/helper;
- a fallback model receives its own configured full timeout.

#### Pinned OAuth operational-boundary gate — blocking

Using the real Codex 0.144.4 runtime and a deterministic local capture backend, with no real OpenAI account/credential, preserve the known 2026-08-20 observations and prove:

- ephemeral thread;
- `environments: []`;
- AEP-requested `instructionSources: []`;
- no user project/workspace/AGENTS source supplied by AEP;
- empty source MCP envelope => zero AEP-supplied MCP operational tools;
- N source MCP tools => exactly N mapped AEP/MCP tools;
- `update_plan` has no external operational effect;
- `web_search` is provider-side/public information retrieval only and cannot operate user infrastructure or read AEP private host state;
- `request_user_input` is bounded/rejected when no interactive source exists;
- `view_image` cannot read arbitrary local AEP/private credential files, or is disabled/refused before such access;
- shell/filesystem/workspace metadata does not grant callable local authority;
- no native MCP/plugin/app/connector/browser-control/sub-agent/collaboration route can bypass the AEP MCP path to user infrastructure;
- generic system skills/runtime context contain no user project/private credential content and grant no operational authority;
- dynamic MCP tool call returns through `item/tool/call` to the fake MCP path;
- unexpected command/file/permission request is never approved;
- no durable AEP thread/session/reasoning history remains.

The actual outbound provider request and the runtime behavior of the injected native facilities must be captured/tested; checking only the AEP `thread/start` payload is insufficient.

Failure means an unavoidable operational/private-host side channel exists. The mere presence of permitted native reasoning/information helpers is **not** a failure.

### Acceptance

Lot 2 has no public execution source, so real HAOS acceptance is limited to what is meaningful for the new runtime mechanics. Independent review and CI must provide the functional engine evidence, followed by a HAOS deployment/start/runtime smoke sufficient to validate dependencies/AppArmor changes. Lot 2 is accepted only after that evidence is reviewed; CI green alone is not acceptance.

## Lot 3 — standalone API, authentication and durable result lifecycle

Status: **accepted on HAOS in 0.5.5**.

### Goal

Make Agent Execution Plane fully useful independently of Agent Control Plane.

### Scope

- standalone opaque Bearer credential create/rotate/revoke in Ingress;
- one-way credential verifier storage;
- `POST /api/v1/execute`;
- `GET /api/v1/executions/{id}`;
- `POST /api/v1/executions/{id}/ack`;
- exact request contract for objective/input/MCP endpoint/optional MCP Bearer/**exact caller-selected MCP operational capability envelope**/optional result schema;
- caller cannot select model;
- AEP does not derive the standalone MCP capability envelope from `tools/list`;
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
- caller MCP capability envelope remains execution-scoped;
- request/result/body bounds.

### HAOS acceptance

Run a real standalone execution against a configured model and a test MCP server whose inventory contains both requested and unrelated tools. Confirm only the caller-supplied envelope reaches the model **as AEP/MCP operational tools**, while permitted provider-native reasoning/information helpers remain separate; retrieve the result, prove the engine remains blocked before ACK, ACK it, then prove a new execution is accepted. Repeat the pending-result step across an App restart.

Acceptance of this lot proves the independence invariant: Execution Plane is useful with no ACP installed/configured.

Real HAOS acceptance completed on **2026-08-21** with AEP **0.5.5**, commit `aba385af34cba3f856a4c155e8dd5d1e90f01c6b`, and green CI run `32448390300` (59 tests). Manual acceptance covered standalone authentication/contract errors, durable GET/ACK lifecycle, blocked pending-result behavior, a real ChatGPT OAuth execution with the exact caller-supplied `ha_get_overview` capability, successful AEP dynamic-tool dispatch through HA-MCP to Home Assistant with `mcp_effect_possible=true`, and the 4 MiB body bound. During acceptance, 0.5.4 exposed a Codex helper execution denial; 0.5.5 corrected AppArmor for the complete installed Codex executable inventory and added CI coverage so future Codex helpers cannot silently escape the confinement allow-list.

## Lot 4 — Agent Control Plane boundary

Status: **implemented in 0.6.0 and corrected in 0.6.1; HAOS acceptance pending**.

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
- treat ACP `allowed_capabilities` as authoritative for MCP operational model visibility;
- keep ACP lifecycle tools (`jobs_claim_v1`, heartbeat, complete, fail and other boundary operations) out of the model envelope;
- use ACP's MCP `tools/list` only to verify the claimed capability descriptors remain technically present/applicable, never to choose authorized capabilities;
- keep permitted provider-native reasoning/information helpers separate from ACP's authorization envelope and prevent them from becoming infrastructure side channels;
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

- `jobs_claim_v1.job.allowed_capabilities` becomes exactly the AEP-supplied MCP operational model envelope;
- lifecycle tools remain AEP-boundary-only and never become model-visible;
- virtual capability effective schemas match the claim envelope;
- an ACP `tools/list_changed` event does not broaden the frozen MCP model envelope;
- permitted provider-native reasoning/information helpers do not broaden ACP's operational authorization and cannot directly reach ACP-managed infrastructure;
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
5. confirm the model sees exactly the job's `allowed_capabilities` **as its AEP/MCP operational tools**, none of the ACP lifecycle tools, and only separately permitted provider-native reasoning/information helpers;
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
- final provider-native helper versus operational-MCP boundary review;
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
- validate permitted provider-native reasoning/information helpers without operational side-channel behavior;
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
