# Agent Execution Plane — Technical Design

Status: **technical design fixed for implementation**.

This document translates the validated product behavior in `PROJECT_BRIEF.md` into a concrete implementation design. It does not create new product responsibilities. If an implementation detail conflicts with the project brief or the root architecture charter, the narrower Execution Plane product boundary wins and the conflicting detail must be corrected.

## 1. Design goal

Agent Execution Plane remains one small execution engine:

`source -> execution engine -> configured model + source-supplied MCP operational capability envelope + permitted provider-native reasoning helpers -> result -> source`

There is one execution path. Agent Control Plane and the standalone API are thin boundary adapters around that same path; they are not separate modes with separate reasoning semantics.

The implementation must remain understandable without introducing a generic WorkSource framework, workflow engine, scheduler, task database, connector catalogue or authorization policy engine.

The source defines the execution contract. AEP applies it. In particular, AEP never derives authorization from MCP discovery and never replaces the source-supplied MCP operational capability envelope with a capability set of its own.

Provider-native reasoning/information helpers are separate provider mechanics. They may support reasoning, planning or public information retrieval, but they must never become an alternate operational connector path to user infrastructure or AEP private host state.

## 2. Runtime and dependency baseline

The App uses the same proven HAOS-oriented Python foundation as Agent Control Plane where that foundation is generic and appropriate:

- Python runtime on the Home Assistant base image;
- Starlette for HTTP administration/API surfaces;
- Uvicorn for listeners;
- the Python MCP SDK for Streamable HTTP MCP client sessions;
- `jsonschema` for caller-provided output contracts and local argument/schema validation;
- `httpx` for model-provider HTTP communication;
- standard-library `sqlite3` for the small durable state store;
- authenticated encryption for reversible secrets, with an App-local key stored separately under `/data/private`.

Dependencies are pinned. The App runs as an unprivileged runtime user after the minimal startup work required to prepare `/data`.

No provider SDK is required in the execution core. Ollama-compatible and OpenAI-compatible behavior stays behind small HTTP adapters so adding another provider later does not change the engine state machine.

## 3. HAOS packaging and listeners

The App follows the proven two-listener shape used by Agent Control Plane, without inheriting ACP business behavior.

### Administration listener

- fixed container port `8099`;
- reachable through Home Assistant Ingress;
- not published as a normal host port;
- validates the Ingress boundary in the same defensive manner as ACP;
- serves the administration UI and administration JSON endpoints only.

### Standalone API listener

- fixed container port `8098`;
- exposed in `config.yaml` as a normal HAOS App network port;
- host-side port mapping is user-configurable through the Home Assistant App **Network** configuration;
- the execution API requires the opaque standalone Bearer credential;
- health endpoints expose no secrets or execution payloads.

Using a fixed internal port and HAOS's configurable host-port mapping avoids inventing a second port-configuration mechanism inside the application.

### Health semantics

`/health/live` reports only that the process is alive. `/health/ready` reports that the App itself has initialized successfully: configuration/persistence are usable and listeners are running.

External ACP/model/MCP unavailability does **not** make the App unready and must not create a HAOS watchdog restart loop. Those dependencies are reported as operational/degraded states in the Ingress UI instead.

## 4. Common in-memory execution request

Both boundaries translate their input into one small internal `ExecutionRequest` value containing only what the engine needs:

- execution identifier and source reference;
- source-provided objective/instruction;
- source-provided JSON input;
- MCP endpoint information required for this execution;
- optional MCP Bearer credential;
- the exact **source-supplied model-invocable MCP operational capability envelope** for this execution;
- optional caller-provided result JSON schema;
- source lifecycle guard where one exists, such as the ACP lease.

The MCP capability envelope is data supplied by the source boundary. It is not calculated by the execution core.

For ACP, it is populated directly from the claimed job's `allowed_capabilities`. For standalone, it is populated directly from the request contract. The common engine never queries a broader MCP inventory and makes a policy decision about what subset should be model-visible.

Provider-native reasoning/information helpers are not fields of `ExecutionRequest` and are not source-selected authorization data. Their availability and safe handling belong to the provider adapter/runtime contract.

This value is an internal data structure, not a generic plugin framework or public orchestration abstraction.

The engine returns one `ExecutionOutcome`: either the final model output or a bounded factual technical failure.

## 5. Single execution state machine

One global execution slot is enforced atomically.

The useful runtime states are deliberately small:

`idle -> preparing -> running -> pending_result -> idle`

A restart can additionally recover an `interrupted` active reference long enough to report/resolve it truthfully.

There is no waiting queue inside Execution Plane.

ACP polling and standalone submission both acquire the same slot. A standalone submission is accepted only if the slot is free. The ACP poller attempts to claim work only while the slot is free. The same atomic state guard prevents both boundaries from owning the slot simultaneously; no source-priority scheduler is introduced.

## 6. Source boundaries

### 6.1 Agent Control Plane boundary

Execution Plane stores an administrator-configured ACP MCP endpoint and the reversible protected Bearer credential for one ACP worker identity.

While the slot is free and at least one enabled compatible model exists, the boundary polls `jobs_claim_v1` every second. A successful claim is translated directly into the common execution request using:

- ACP's objective;
- ACP's input;
- ACP's `allowed_capabilities` exactly as returned by the claimed job;
- ACP's required report schema;
- the source lifecycle/lease material required only by this boundary.

The same ACP Streamable HTTP MCP surface is used for:

- claim;
- heartbeat;
- virtual task capability calls for the claimed job;
- completion/failure delivery.

The ACP MCP server can expose both source-boundary lifecycle tools and virtual task capabilities on the same authenticated surface. Those categories must remain separated inside AEP:

- `jobs_claim_v1`, `jobs_heartbeat_v1`, `jobs_complete_v1`, `jobs_fail_v1` and other source-boundary operations are called only by the ACP boundary;
- connection validation requires the exact lifecycle input signatures, including the opaque `completion_key` used for idempotent complete/fail delivery;
- only MCP capabilities named in the claimed job's `allowed_capabilities` can enter the source-authorized operational model envelope;
- a lifecycle tool appearing in `tools/list` must never become model-visible merely because the worker identity is authorized to call it.

ACP remains the sole authority for:

- connector configuration and credentials;
- connector inventory discovery;
- task/tool selection;
- virtual tool naming;
- effective input schemas;
- `fixed_arguments_v1` and other ACP-owned restrictions;
- authorization and fail-closed capability resolution at invocation time.

AEP does not duplicate or reinterpret any of those mechanics.

Permitted provider-native reasoning/information helpers remain outside ACP's operational capability envelope and may not be used to reach or control ACP-managed infrastructure directly.

ACP lease values remain ACP policy. Execution Plane tracks and respects the lease but never derives its model timeout from ACP's lease duration.

### 6.2 Standalone API boundary

Versioned API routes are:

- `POST /api/v1/execute`;
- `GET /api/v1/executions/{execution_id}`;
- `POST /api/v1/executions/{execution_id}/ack`.

`POST /execute` accepts:

- `objective`;
- `input` as any valid JSON value;
- `mcp.url`;
- optional `mcp.bearer_token`;
- exact `mcp.tools` descriptors defining the caller's model-invocable MCP operational capability envelope;
- optional `result_schema`.

The standalone caller is the source authority for that execution. AEP does not turn a broader MCP server inventory into an authorization policy. It only verifies and executes the exact MCP envelope supplied by the caller.

Provider-native reasoning/information helpers, where supported by the selected provider, remain provider mechanics and are not caller-selected operational capabilities.

The caller never selects a model.

A successful submit returns an opaque execution ID. A busy engine returns a clear conflict response and stores no queue entry. `GET` retrieves status/result without releasing it. Only `ack` removes a pending standalone result and frees the slot.

Caller-supplied standalone MCP endpoint/credential/tool data is execution-scoped. It is never promoted into permanent connector configuration and is not persisted for later reuse.

## 7. Standalone authentication

The standalone API uses one application-managed opaque Bearer credential.

- generated cryptographically by Execution Plane;
- shown once when created or rotated;
- stored only as a verifier, never recoverable in clear text;
- revocable/replaceable from Ingress;
- absent by default until the administrator creates it.

Credential comparison is constant-time. Authentication failures disclose no verifier details.

The administration UI itself relies on the HA Ingress trust boundary and is not exposed through the standalone API port.

## 8. Model configuration

A configured model is the user-facing unit. There is no separate “model profile” concept.

Each model stores:

- internal ID;
- administrator-visible name;
- provider family: `ollama_compatible`, `openai_compatible` or `openai_chatgpt_oauth`;
- provider base URL for the two endpoint-based families, and `NULL` for `openai_chatgpt_oauth`;
- provider model identifier;
- optional provider Bearer/API credential;
- enabled/disabled state;
- explicit integer priority/order;
- timeout in minutes;
- last known technical state and bounded diagnostic metadata.

A newly configured model defaults to a **5-minute timeout**. The only product-level validity rule is that the configured timeout is positive; Execution Plane imposes no caller-derived maximum.

Provider credentials are encrypted at rest and are never returned by administration APIs. Editing a model keeps the existing credential unless the administrator explicitly replaces it.

`openai_chatgpt_oauth` has no configurable base URL and no API-key field. Its `encrypted_credential` is always `NULL`; OAuth persistence and refresh remain exclusively owned by the official Codex runtime under `/data/private/codex-home`.

## 9. Model validation and health

Creation and technical editing are validate-before-commit operations.

A candidate configuration is tested before it replaces stored state. Failure leaves the previous configuration unchanged.

### Ollama-compatible

The adapter uses the native Ollama-compatible HTTP API, principally `/api/show`/model metadata and `/api/chat`. The technical validation confirms endpoint/authentication/model availability and declared tool capability where the endpoint provides it. Native JSON-schema `format` is used when a result schema is required and supported.

### OpenAI-compatible

For version one, “OpenAI-compatible” means an endpoint compatible with the widely implemented `/v1/models` and `/v1/chat/completions` contract needed for chat tool/function calling. Provider credentials are optional so local compatible servers remain usable.

Because generic OpenAI-compatible model metadata does not reliably prove tool-call behavior, the explicit administrator-triggered creation/edit validation may perform one tiny bounded inference/tool-call probe. The UI/documentation must state that this manual validation can consume provider tokens/quota. This is not an automatic health check.

### OpenAI ChatGPT OAuth

The `openai_chatgpt_oauth` adapter uses the official, exactly pinned `openai-codex==0.144.4` SDK distribution and its matching `openai-codex-cli-bin==0.144.4` runtime. AEP communicates with `codex app-server` only through local stdio JSONL and exposes no Codex network listener.

Codex uses the dedicated `/data/private/codex-home` with `forced_login_method = "chatgpt"` and `cli_auth_credentials_store = "file"`. The child environment explicitly sets `CODEX_HOME` and removes `OPENAI_API_KEY`, `CODEX_API_KEY` and `CODEX_ACCESS_TOKEN`. AEP uses only a bounded account/catalogue wrapper for device-code login, login cancellation, `account/read`, `account/logout` and `model/list`; it never uses `chatgptAuthTokens`, parses OAuth tokens or calls OpenAI directly with them.

Explicit OAuth-model validation performs no inference. It proves a compatible app-server handshake, a ChatGPT-authenticated account and presence of the selected model in `model/list`. Automatic health uses the same non-inference operations. Authentication absence is `Unavailable/auth_required`; runtime or catalogue incompatibility is `Incompatible/runtime_or_model_incompatible`. Neither affects AEP readiness.

The account UI exposes only disconnected, login pending, connected/optional plan type, or a bounded technical error. Email and other personal identifiers are neither stored nor journaled.

### Automatic health

Startup/periodic health uses only non-inference endpoints where that can be done without billable model usage. No automatic prompt is sent merely to refresh a health badge. Where a provider cannot be verified for free, state becomes `Unverified` rather than triggering inference.

Health never changes administrator priority or enabled/disabled state.

### OAuth execution boundary and native-helper characterization

Lot 2 may use the pinned runtime's `thread/start.dynamicTools` only after proving that the **AEP-supplied MCP operational tool surface** is exactly the frozen source MCP envelope and that any additional Codex-native facilities do not create an operational side channel around MCP/ACP.

The correct invariant is not “Codex must expose zero native tools”. Codex may retain provider-native reasoning/information helpers required for its normal reasoning behavior, including public Web search or internal planning, provided they cannot operate user infrastructure, access AEP private host/filesystem state, obtain connector credentials, invoke an alternate MCP/connector path, or otherwise bypass the source-authorized operational envelope.

A real preflight performed on **2026-08-20** with the pinned Codex 0.144.4 runtime, a deterministic local HTTP capture backend and no real OpenAI identity/credential established the following facts about the actual provider request:

- the AEP dynamic tool is transmitted correctly;
- `ephemeral: true` is respected;
- `instructionSources: []` is respected;
- Codex also injects native tools including `update_plan`, `request_user_input`, `view_image` and `web_search`;
- Codex injects generic permission instructions and a catalogue of five system skills;
- `environment_context` contains shell/filesystem/workspace metadata;
- `runtimeWorkspaceRoots` contains the dedicated `CODEX_HOME` root.

This preflight **disproves the former zero-native-tools assumption but does not by itself make OAuth execution incompatible**. The blocking question is whether any injected native facility provides real operational or private-host access outside the AEP-controlled MCP path.

Before OAuth execution is enabled, CI/implementation analysis must characterize the actual 0.144.4 behavior and prove at least:

- the AEP-supplied MCP dynamic tools correspond exactly one-to-one to the frozen source MCP envelope; no unrelated MCP capability is added;
- an empty source MCP envelope produces zero AEP-supplied MCP operational tools, even though permitted Codex-native helpers may remain present;
- `update_plan` is internal reasoning/planning state only and cannot operate external infrastructure;
- `web_search`, if enabled by the runtime, is limited to provider-side/public information retrieval and is not an arbitrary local-network/vendor-control transport; AEP-owned credentials and hidden MCP secrets are never injected into it;
- `request_user_input` cannot silently turn an unattended execution into an unbounded wait; if the current AEP source has no interactive user channel, the request is rejected or converted to a bounded factual execution outcome according to the provider adapter contract;
- `view_image` cannot be used to read arbitrary AEP host files, `/data/private`, Codex OAuth credential files or other local secrets; if the pinned runtime cannot prevent such access, the capability must be disabled/refused or OAuth execution is incompatible;
- shell/filesystem/workspace metadata in `environment_context` does not imply callable local shell/filesystem authority; no command/file/permission request capable of local access is automatically approved;
- `runtimeWorkspaceRoots` and system skills do not expose user project data, OAuth credential contents or another operational capability; generic provider/runtime instructions may remain only if they do not add a new business objective or operational authority;
- no native Codex MCP server/client, plugin, app, connector, browser-control path, sub-agent or collaboration facility can reach user infrastructure outside the source-authorized MCP path;
- `item/tool/call` for AEP dynamic tools returns through AEP's validated MCP loop;
- OAuth execution threads remain ephemeral and no durable reasoning/session history is intentionally retained by AEP.

The proof must inspect/capture the request and runtime behavior actually produced by the pinned binary. Checking only AEP's intended `thread/start` payload is insufficient.

If a native Codex facility provides an unavoidable operational or private-host side channel that AEP cannot disable, reject or confine, `openai_chatgpt_oauth` is execution-incompatible. Do not weaken the source-authorized MCP operational boundary and do not replace ChatGPT OAuth with an OpenAI Platform API key.

## 10. Provider adapter contract

The execution engine knows only a small provider adapter contract capable of:

- validating configuration;
- sending the current conversation plus the exact frozen **AEP-supplied MCP operational capability descriptors**;
- exposing/handling only provider-native reasoning/information helpers that satisfy the provider-specific safety boundary;
- receiving either final assistant content, AEP/MCP tool calls or permitted provider-native helper activity;
- attaching MCP tool results to the next provider turn;
- requesting structured output from a caller-provided schema when supported;
- returning bounded usage/diagnostic metadata.

Provider adapters normalize protocol shapes but do not add business instructions and do not select MCP operational capabilities.

If a provider imposes naming constraints incompatible with an MCP tool name, the adapter may use a deterministic collision-safe **one-to-one transport alias**. Such an alias must map reversibly to exactly one source MCP capability and must not change its description, input schema or authorization meaning.

Provider-native helpers are never transport aliases for hidden operational capabilities.

Provider streaming is not required in version one. Non-streaming calls keep the state machine and timeout handling deterministic.

The model's configured timeout wraps the **entire model attempt**, including all provider turns, permitted provider-native helper activity and MCP exchanges for that model. Individual network operations also use the remaining attempt deadline so no single socket call can outlive it.

## 11. Model context construction

Execution Plane does not create a hidden business/system prompt.

The source objective and source input are transmitted deterministically as source material. **AEP-supplied MCP operational tool definitions** come only from the frozen source-supplied MCP envelope and are supplied through the provider's supported tool/function-calling mechanism. A source-provided result schema is supplied through the provider's structured-output mechanism where available and is always validated locally before delivery.

Source-boundary lifecycle tools and unrelated MCP inventory entries are not model context.

Provider-native generic reasoning/information helpers and provider/runtime system instructions may additionally be present according to the provider adapter contract. They must remain distinguishable from AEP-supplied MCP operational tools and must not add a new business objective, operational authorization or infrastructure side channel.

Provider-specific wrappers needed to serialize the same objective/input are formatting only and must not infer additional goals, policy or context.

For Codex app-server execution, AEP explicitly requests `instructionSources: []` and does not supply a user project/workspace/AGENTS source. Generic Codex system skills/runtime context that the pinned runtime injects may remain only if the OAuth characterization gate proves they do not expose private local content or operational authority.

Provider reasoning/thinking fields are neither persisted nor logged.

## 12. MCP client mechanics and capability-envelope consistency

Version one supports MCP **Streamable HTTP** for model-invocable operational capabilities.

For each execution, Execution Plane receives a frozen MCP capability envelope from the source before the model runs.

For each capability in that envelope, AEP performs only **technical consistency validation** against the supplied MCP session:

1. initialize one MCP client session to the supplied endpoint;
2. retrieve the tool inventory with paginated `tools/list` as required;
3. locate each source-supplied capability by its exact MCP name;
4. confirm that the effective input schema matches the source-supplied descriptor;
5. freeze the validated source MCP envelope for the model attempt/execution;
6. expose exactly that frozen source envelope as AEP-supplied MCP operational tools to the provider/model;
7. keep any permitted provider-native reasoning/information helpers separate from that MCP envelope;
8. validate model-produced MCP arguments locally against the same source-supplied effective schema;
9. invoke only through `tools/call` using the exact MCP tool name after reversing any provider-only transport alias;
10. close the execution MCP session when the execution ends.

This mechanism does **not** authorize capabilities. It only verifies that the source MCP contract can still be executed against the MCP surface it references.

Tools returned by MCP `tools/list` that are absent from the source envelope are not model MCP tools. AEP does not classify them, authorize them, deny them semantically or use them to construct a replacement envelope. They remain outside the current execution contract.

For ACP this distinction is mandatory because the same MCP server also exposes AEP boundary lifecycle tools. Those lifecycle tools are boundary-only mechanics and must never be exposed to the reasoning model. The model-visible ACP MCP envelope comes exclusively from the task virtual capabilities carried in the claimed job's `allowed_capabilities`.

A missing source capability or effective-schema mismatch fails closed as a factual technical contract inconsistency. Execution Plane never silently substitutes a changed schema or broadens/narrows the source MCP envelope.

If an MCP `tools/list_changed` notification occurs during an execution, AEP must not silently refresh the model-visible MCP capability set. It may revalidate the already-frozen envelope before a subsequent dispatch when needed; if the source contract can no longer be proven applicable, execution fails closed. New MCP capabilities are never added mid-execution.

## 13. Tool-call technical validation

AEP distinguishes **source-authorized MCP operational tool calls** from **permitted provider-native reasoning/information helper activity**.

When the model requests an AEP/MCP operational tool:

1. resolve any provider-only transport alias back to the exact source capability;
2. require that capability to exist in the frozen source MCP envelope;
3. require valid JSON arguments;
4. validate arguments locally against the frozen effective input schema;
5. enforce argument and dispatch-count bounds;
6. only then issue MCP `tools/call`.

Unknown AEP/MCP tool or invalid arguments result in a bounded technical failure with **zero MCP dispatch**.

A provider-native helper is never routed to ACP as though it were an MCP capability and never gains operational authorization from its native status. Its handling is limited to the provider-specific helper contract established by the OAuth/provider characterization gate.

AEP does not judge whether an MCP argument is operationally safe, semantically authorized or desirable. In ACP mode those decisions and any server-side fixed argument injection remain ACP responsibilities. AEP validates only the technical contract it was supplied.

## 14. Side-effect boundary and fallback

The no-replay boundary is conservative for **operational MCP effects**.

`mcp_effect_possible` becomes true **as soon as a `tools/call` request is dispatched to the MCP server**. A lost response can still mean that the upstream action occurred, so waiting for a successful response would be unsafe.

Permitted provider-native reasoning/information helper activity such as internal planning or public Web search does not set `mcp_effect_possible`, because such helpers are not allowed to create user-infrastructure operational effects. If a provider-native facility can create such an effect, it violates the provider boundary and must not be enabled as a helper.

Consequences:

- provider/model technical failure before any MCP dispatch may fall back to the next enabled compatible model;
- output-contract failure before any MCP dispatch may fall back to the next model;
- once any MCP call has been dispatched, no automatic model fallback is allowed;
- an MCP transport/protocol/tool failure terminates the execution factually rather than trying another model, because switching models does not repair the MCP dependency and may cause replay ambiguity.

Every fallback starts from the original source request and the original frozen MCP capability envelope. No failed-model conversation or reasoning is carried forward.

## 15. Result schema handling

If the source supplies no result schema, the final model text/JSON result is returned as produced within transport bounds.

If the source supplies a JSON schema:

- the provider adapter uses its supported structured-output mechanism where available;
- the final candidate is parsed/validated locally with `jsonschema`;
- no unbounded “repair conversation” is introduced;
- a schema violation is a factual output-contract technical failure;
- fallback is allowed only if no MCP call has been dispatched; otherwise the failure is returned without replay.

Execution Plane does not judge whether a schema-valid result is semantically “good”.

## 16. Technical bounds

Bounds exist to prevent accidental or hostile unbounded memory/tool loops without turning the App into a business policy engine.

Version-one defaults:

- standalone request body: 4 MiB maximum;
- final API/result body: 4 MiB maximum;
- maximum source-supplied model-invocable MCP capabilities in one execution: 128;
- maximum MCP tool dispatches in one model attempt: 128;
- maximum individual MCP tool argument document: 512 KiB;
- maximum individual MCP tool result accepted into model context: 2 MiB;
- objective/input/schema/tool-descriptor subdocuments must each fit inside the overall request bound.

Crossing a bound is a technical failure; content is not silently truncated because truncation could change meaning.

These are AEP implementation safety bounds, not ACP authorization limits. If a source supplies an MCP envelope beyond AEP's documented technical capacity, AEP rejects the execution rather than selecting a smaller subset.

Provider-native helper behavior remains subject to the whole-attempt deadline and provider/runtime bounds; it must not be used to bypass AEP's MCP argument/result limits for operational work.

## 17. Persistence schema and secret handling

SQLite is used because durable state is small, local and transactional.

The first schema generation contains only four conceptual areas:

### `models`

Configured model definitions, ordering, state and encrypted provider credential.

### `settings`

Small App settings plus encrypted ACP worker credential and ACP endpoint configuration.

### `active_execution`

At most one row containing only the source kind, execution/source reference, start metadata and the minimum protected source lifecycle material needed to report an interruption after restart. It does not contain the full model conversation, a connector catalogue or a durable copy of ACP governance state.

### `pending_result`

At most one row containing the final result/technical outcome plus the minimum source delivery information required until explicit acceptance/acknowledgement.

A separate random encryption key lives under `/data/private` with restrictive file permissions and AppArmor rules. Standalone API credentials remain one-way verifiers; reversible encryption is used only for secrets the App must later send outward, such as model and ACP boundary credentials.

No completed execution history is kept in SQLite.

Provider-native helpers never receive AEP private encryption material, MCP credentials or OAuth token contents from AEP.

## 18. Restart recovery

Startup recovery is deterministic.

### Pending result found

Restore it exactly, keep the execution slot blocked, and resume the source-specific delivery/acknowledgement lifecycle without rerunning the model.

### Active execution found without final result

Never rerun it.

- For ACP, attempt to report an interrupted execution with the saved source reference/lease material when ACP is reachable. If ACP definitively reports that the lease/job is already terminal or no longer owned, treat source ownership as resolved and clear the local interruption reference. If ACP is unreachable, retain the reference and do not claim new work until the interruption can be reconciled.
- For standalone operation, convert the interrupted execution into one pending factual technical result for the same execution ID. The caller can retrieve and acknowledge it normally.

This prevents silent replay while keeping the single-slot invariant understandable after a crash.

## 19. ACP lease handling

ACP heartbeat runs only while an ACP execution is active and while the lease remains valid.

A transient heartbeat failure does not immediately abort while the currently issued lease is indisputably valid. Heartbeat restoration is attempted within that validity window.

Once validity can no longer be guaranteed:

- stop the model attempt;
- dispatch no new MCP tool call;
- produce/report an interruption according to ACP's existing contract.

The ACP lease is never used as a maximum allowed configured model timeout.

## 20. Pending result delivery

### ACP

A completed result is persisted before delivery. Delivery is retried every second with the same result; the model is never rerun. On ACP acceptance, the row is deleted and the slot becomes free.

A definitive ACP refusal that cannot be automatically resolved leaves the result visible as stuck/pending for administrator recovery rather than silently deleting it.

### Standalone

The result remains available through `GET` until explicit `POST .../ack`. Only acknowledgement deletes it and frees the slot.

Both boundaries expose the confirmed Ingress action **Abandon pending result** as the exceptional manual escape hatch.

## 21. Administration UI

The Ingress UI reuses Agent Control Plane's visual language rather than creating a second design system.

Required shell behavior:

- `Agent Execution Plane vX.Y.Z` in the header, with the version next to the product name;
- French/English switch;
- light/dark mode switch;
- responsive layout compatible with HA Ingress;
- no external frontend CDN/runtime dependency.

Initial functional views remain small:

- **Overview**: engine state, source/API state, current execution, pending result and dependency diagnostics;
- **Models**: add/test/edit/delete, enabled state, priority ordering and per-model timeout;
- **Connections / API**: ACP endpoint/worker credential management and standalone API credential create/rotate/revoke state;
- **Diagnostics**: bounded operational information useful for troubleshooting, without a historical job/audit product.

No page becomes a task editor, connector catalogue, capability selector, authorization editor or execution-history database.

## 22. Logging and redaction

Logs are operational, bounded and non-semantic.

Allowed examples include:

- startup/shutdown and schema version;
- listener readiness;
- model/provider name and state transitions;
- source kind/execution ID;
- phase transitions and durations;
- MCP tool **name** for dispatch/completion/failure metadata;
- bounded provider/MCP error codes;
- result delivery/acknowledgement state.

Never log:

- model/API/ACP/MCP credentials;
- objective or input payloads;
- MCP tool arguments or MCP tool results;
- provider-native helper queries/results when they may contain source material;
- final result bodies;
- model reasoning/thinking content;
- standalone Bearer tokens;
- ACP connector endpoint/credential material or hidden fixed arguments.

Administration diagnostics follow the same redaction rules.

## 23. AppArmor and process boundary

The App has its own `agent_execution_plane` AppArmor profile.

The policy is derived from the executable/runtime inventory of this App, not copied blindly from ACP. It permits only:

- the base/s6 startup executables actually required;
- Python/runtime libraries and read-only App code;
- the pinned Codex runtime executable needed by the OAuth provider;
- required outbound IPv4/IPv6 stream networking;
- writes to `/data`, tightly scoped `/data/private`, `/run` and temporary runtime paths;
- the minimum startup capabilities required to prepare data ownership and drop to the unprivileged runtime user.

No shell, SSH client, browser runtime, Docker socket, Home Assistant API privilege or broad host filesystem access is granted merely because a provider advertises a native helper. Provider-native public Web search must remain provider-side and must not justify installing a local browser or broadening AppArmor.

Any Codex command/file/permission request that would require local shell/filesystem authority remains denied unless a later explicit product decision changes the AEP responsibility boundary; the current Lot 2 does not do so.

CI records executable inventory and HAOS acceptance verifies startup, normal operation, shutdown and restart under the enforced profile.

## 24. Documentation

Before release, repository documentation includes complete English and French coverage for:

- purpose and architecture boundary;
- explicit ACP/AEP responsibility separation;
- distinction between source-authorized MCP operational capabilities and permitted provider-native reasoning/information helpers;
- HAOS installation and Network port configuration;
- Ingress UI;
- model configuration for all provider families;
- ACP integration, including `allowed_capabilities` as the authoritative MCP operational capability envelope and ACP lifecycle tools as AEP-boundary-only operations;
- standalone API authentication and exact request/result/ack lifecycle;
- standalone source-supplied MCP capability-envelope contract;
- persistence/restart behavior;
- security/redaction/AppArmor boundaries;
- troubleshooting and known compatibility requirements.

The standalone API examples are directly usable and make clear that `GET` does not free the slot; `ack` does.

## 25. CI and acceptance strategy

CI must prove mechanics without requiring real paid providers:

- unit tests for persistence, state transitions, auth, priority/fallback and bounds;
- fake Ollama-compatible and OpenAI-compatible HTTP providers including tool calls, errors and structured output;
- fake Streamable HTTP MCP servers containing both source-envelope tools and unrelated/lifecycle-like tools;
- proof that only the source-supplied MCP envelope reaches the model as **AEP-supplied MCP operational tools**;
- proof that an empty source MCP envelope stays empty as an AEP/MCP tool surface despite a non-empty MCP inventory;
- provider-native reasoning/information helpers may coexist only under their separately tested provider boundary and must never be counted as source-authorized MCP tools;
- missing/schema-mismatched source capability failures;
- standalone API end-to-end tests;
- ACP contract integration tests against the actual ACP contract surface or a contract-faithful fixture, including `allowed_capabilities` and lifecycle/tool separation;
- restart recovery tests for active and pending states;
- container build/smoke tests;
- AppArmor executable-inventory validation;
- secret/redaction tests;
- bilingual/theme/version UI smoke assertions.

For `openai_chatgpt_oauth`, CI additionally captures the actual provider request/runtime behavior produced by Codex 0.144.4 and proves both:

1. **MCP integrity:** the AEP-supplied dynamic MCP tools correspond exactly to the frozen source MCP envelope and unrelated MCP tools never become model-visible;
2. **native-helper confinement:** every additional Codex-native tool/context/skill that remains present is non-operational with respect to user infrastructure and AEP private host state, or is explicitly denied/refused before it can perform such access.

The known 2026-08-20 preflight observations (`update_plan`, `request_user_input`, `view_image`, `web_search`, permission instructions, five system skills, `environment_context`, `runtimeWorkspaceRoots`) become regression inputs for this characterization rather than a blanket zero-native-tools failure condition.

Real HAOS acceptance remains mandatory after each implementation lot reaches CI-conformant state.

## 26. Production-data cutoff

Development data is considered disposable only until the first release is explicitly accepted as the production baseline on the user's HAOS installation.

That acceptance establishes the Execution Plane persistence-preservation cutoff. From that point forward, schema evolution must preserve supported existing model/settings/pending state through explicit tested upgrades; clean reinstall/data deletion is no longer an ordinary migration strategy.
