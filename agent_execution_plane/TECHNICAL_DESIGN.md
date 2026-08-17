# Agent Execution Plane — Technical Design

Status: **technical design fixed for implementation planning**.

This document translates the validated product behavior in `PROJECT_BRIEF.md` into a concrete implementation design. It does not create new product responsibilities. If an implementation detail conflicts with the project brief or the root architecture charter, the narrower Execution Plane product boundary wins and the conflicting detail must be corrected.

## 1. Design goal

Agent Execution Plane remains one small execution engine:

`source -> execution engine -> configured model + supplied MCP tools -> result -> source`

There is one execution path. Agent Control Plane and the standalone API are thin boundary adapters around that same path; they are not separate modes with separate reasoning semantics.

The implementation must remain understandable without introducing a generic WorkSource framework, workflow engine, scheduler, task database or capability catalogue.

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
- exact authorized MCP tool descriptors for this execution;
- optional caller-provided result JSON schema;
- source lifecycle guard where one exists, such as the ACP lease.

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

While the slot is free and at least one enabled compatible model exists, the boundary polls `jobs_claim_v1` every second. A claim is translated directly into the common execution request using ACP's source-provided objective/input, allowed capability surface and required report schema.

The same ACP Streamable HTTP MCP surface is used for:

- claim;
- heartbeat;
- exact governed tools for the claimed job;
- completion/failure delivery.

ACP lease values remain ACP policy. Execution Plane tracks and respects the lease but never derives its model timeout from ACP's lease duration.

### 6.2 Standalone API boundary

Versioned API routes are:

- `POST /api/v1/execute`;
- `GET /api/v1/executions/{execution_id}`;
- `POST /api/v1/executions/{execution_id}/ack`.

`POST /execute` accepts the same functional material supplied by ACP:

- `objective`;
- `input` as any valid JSON value;
- `mcp.url`;
- optional `mcp.bearer_token`;
- exact `mcp.tools` descriptors;
- optional `result_schema`.

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
- provider family: `ollama_compatible` or `openai_compatible`;
- provider base URL;
- provider model identifier;
- optional provider Bearer/API credential;
- enabled/disabled state;
- explicit integer priority/order;
- timeout in minutes;
- last known technical state and bounded diagnostic metadata.

A newly configured model defaults to a **5-minute timeout**. The only product-level validity rule is that the configured timeout is positive; Execution Plane imposes no caller-derived maximum.

Provider credentials are encrypted at rest and are never returned by administration APIs. Editing a model keeps the existing credential unless the administrator explicitly replaces it.

## 9. Model validation and health

Creation and technical editing are validate-before-commit operations.

A candidate configuration is tested before it replaces stored state. Failure leaves the previous configuration unchanged.

### Ollama-compatible

The adapter uses the native Ollama-compatible HTTP API, principally `/api/show`/model metadata and `/api/chat`. The technical validation confirms endpoint/authentication/model availability and declared tool capability where the endpoint provides it. Native JSON-schema `format` is used when a result schema is required and supported.

### OpenAI-compatible

For version one, “OpenAI-compatible” means an endpoint compatible with the widely implemented `/v1/models` and `/v1/chat/completions` contract needed for chat tool/function calling. Provider credentials are optional so local compatible servers remain usable.

Because generic OpenAI-compatible model metadata does not reliably prove tool-call behavior, the explicit administrator-triggered creation/edit validation may perform one tiny bounded inference/tool-call probe. The UI/documentation must state that this manual validation can consume provider tokens/quota. This is not an automatic health check.

### Automatic health

Startup/periodic health uses only non-inference endpoints where that can be done without billable model usage. No automatic prompt is sent merely to refresh a health badge. Where a provider cannot be verified for free, state becomes `Unverified` rather than triggering inference.

Health never changes administrator priority or enabled/disabled state.

## 10. Provider adapter contract

The execution engine knows only a small provider adapter contract capable of:

- validating configuration;
- sending the current conversation plus exact tool descriptors;
- receiving either final assistant content or provider tool calls;
- attaching tool results to the next provider turn;
- requesting structured output from a caller-provided schema when supported;
- returning bounded usage/diagnostic metadata.

Provider adapters normalize protocol shapes but do not add business instructions.

Provider streaming is not required in version one. Non-streaming calls keep the state machine and timeout handling deterministic.

The model's configured timeout wraps the **entire model attempt**, including all provider turns and MCP exchanges for that model. Individual network operations also use the remaining attempt deadline so no single socket call can outlive it.

## 11. Model context construction

Execution Plane does not create a hidden business/system prompt.

The source objective and source input are transmitted deterministically as source material. Tool definitions are supplied through the provider's tool/function-calling field. A source-provided result schema is supplied through the provider's structured-output mechanism where available and is always validated locally before delivery.

Provider-specific wrappers needed to serialize the same objective/input are formatting only and must not infer additional goals, policy or context.

Provider reasoning/thinking fields are neither persisted nor logged.

## 12. MCP client mechanics and fail-closed capability handling

Version one supports MCP **Streamable HTTP** for model-invocable capabilities.

For each execution, Execution Plane:

1. initializes one MCP client session to the supplied endpoint;
2. retrieves the tool inventory with paginated `tools/list` as required;
3. verifies that every caller-authorized tool exists and that the effective input schema matches the source-supplied descriptor expected for the execution;
4. exposes only that exact verified subset to the model;
5. validates model-produced arguments locally against the authorized input schema before dispatch;
6. invokes tools only through `tools/call`;
7. closes the execution MCP session when the execution ends.

Unlisted tools discovered from the MCP server are ignored and never shown to the model.

A capability mismatch fails closed. Execution Plane never silently substitutes a changed schema or broadens the list.

## 13. Side-effect boundary and fallback

The no-replay boundary is conservative.

`mcp_effect_possible` becomes true **as soon as a `tools/call` request is dispatched to the MCP server**. A lost response can still mean that the upstream action occurred, so waiting for a successful response would be unsafe.

Consequences:

- provider/model technical failure before any MCP dispatch may fall back to the next enabled compatible model;
- output-contract failure before any MCP dispatch may fall back to the next model;
- once any MCP call has been dispatched, no automatic model fallback is allowed;
- an MCP transport/protocol/tool failure terminates the execution factually rather than trying another model, because switching models does not repair the MCP dependency and may cause replay ambiguity.

Every fallback starts from the original source request and capability surface. No failed-model conversation or reasoning is carried forward.

## 14. Result schema handling

If the source supplies no result schema, the final model text/JSON result is returned as produced within transport bounds.

If the source supplies a JSON schema:

- the provider adapter uses its supported structured-output mechanism where available;
- the final candidate is parsed/validated locally with `jsonschema`;
- no unbounded “repair conversation” is introduced;
- a schema violation is a factual output-contract technical failure;
- fallback is allowed only if no MCP call has been dispatched; otherwise the failure is returned without replay.

Execution Plane does not judge whether a schema-valid result is semantically “good”.

## 15. Technical bounds

Bounds exist to prevent accidental or hostile unbounded memory/tool loops without turning the App into a business policy engine.

Version-one defaults:

- standalone request body: 4 MiB maximum;
- final API/result body: 4 MiB maximum;
- maximum authorized MCP tools in one execution: 128;
- maximum MCP tool dispatches in one model attempt: 128;
- maximum individual tool argument document: 512 KiB;
- maximum individual MCP tool result accepted into model context: 2 MiB;
- objective/input/schema/tool-descriptor subdocuments must each fit inside the overall request bound.

Crossing a bound is a technical failure; content is not silently truncated because truncation could change meaning.

These are implementation safety bounds, not ACP-derived limits.

## 16. Persistence schema and secret handling

SQLite is used because durable state is small, local and transactional.

The first schema generation contains only four conceptual areas:

### `models`

Configured model definitions, ordering, state and encrypted provider credential.

### `settings`

Small App settings plus encrypted ACP worker credential and ACP endpoint configuration.

### `active_execution`

At most one row containing only the source kind, execution/source reference, start metadata and the minimum protected source lifecycle material needed to report an interruption after restart. It does not contain the full model conversation or a durable copy of the source payload.

### `pending_result`

At most one row containing the final result/technical outcome plus the minimum source delivery information required until explicit acceptance/acknowledgement.

A separate random encryption key lives under `/data/private` with restrictive file permissions and AppArmor rules. Standalone API credentials remain one-way verifiers; reversible encryption is used only for secrets the App must later send outward, such as model and ACP credentials.

No completed execution history is kept in SQLite.

## 17. Restart recovery

Startup recovery is deterministic.

### Pending result found

Restore it exactly, keep the execution slot blocked, and resume the source-specific delivery/acknowledgement lifecycle without rerunning the model.

### Active execution found without final result

Never rerun it.

- For ACP, attempt to report an interrupted execution with the saved source reference/lease material when ACP is reachable. If ACP definitively reports that the lease/job is already terminal or no longer owned, treat source ownership as resolved and clear the local interruption reference. If ACP is unreachable, retain the reference and do not claim new work until the interruption can be reconciled.
- For standalone operation, convert the interrupted execution into one pending factual technical result for the same execution ID. The caller can retrieve and acknowledge it normally.

This prevents silent replay while keeping the single-slot invariant understandable after a crash.

## 18. ACP lease handling

ACP heartbeat runs only while an ACP execution is active and while the lease remains valid.

A transient heartbeat failure does not immediately abort while the currently issued lease is indisputably valid. Heartbeat restoration is attempted within that validity window.

Once validity can no longer be guaranteed:

- stop the model attempt;
- dispatch no new MCP tool call;
- produce/report an interruption according to ACP's existing contract.

The ACP lease is never used as a maximum allowed configured model timeout.

## 19. Pending result delivery

### ACP

A completed result is persisted before delivery. Delivery is retried every second with the same result; the model is never rerun. On ACP acceptance, the row is deleted and the slot becomes free.

A definitive ACP refusal that cannot be automatically resolved leaves the result visible as stuck/pending for administrator recovery rather than silently deleting it.

### Standalone

The result remains available through `GET` until explicit `POST .../ack`. Only acknowledgement deletes it and frees the slot.

Both boundaries expose the confirmed Ingress action **Abandon pending result** as the exceptional manual escape hatch.

## 20. Administration UI

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
- **Connections / API**: ACP endpoint/credential management and standalone API credential create/rotate/revoke state;
- **Diagnostics**: bounded operational information useful for troubleshooting, without a historical job/audit product.

No page becomes a task editor, connector catalogue or execution-history database.

## 21. Logging and redaction

Logs are operational, bounded and non-semantic.

Allowed examples include:

- startup/shutdown and schema version;
- listener readiness;
- model/provider name and state transitions;
- source kind/execution ID;
- phase transitions and durations;
- bounded provider/MCP error codes;
- result delivery/acknowledgement state.

Never log:

- model/API/ACP/MCP credentials;
- objective or input payloads;
- tool arguments or tool results;
- final result bodies;
- model reasoning/thinking content;
- standalone Bearer tokens.

Administration diagnostics follow the same redaction rules.

## 22. AppArmor and process boundary

The App has its own `agent_execution_plane` AppArmor profile.

The policy is derived from the executable/runtime inventory of this App, not copied blindly from ACP. It permits only:

- the base/s6 startup executables actually required;
- Python/runtime libraries and read-only App code;
- required outbound IPv4/IPv6 stream networking;
- writes to `/data`, tightly scoped `/data/private`, `/run` and temporary runtime paths;
- the minimum startup capabilities required to prepare data ownership and drop to the unprivileged runtime user.

No shell, SSH client, browser runtime, Docker socket, Home Assistant API privilege or host filesystem access is granted unless later implementation evidence proves it is actually required for Execution Plane's own responsibility.

CI records executable inventory and HAOS acceptance verifies startup, normal operation, shutdown and restart under the enforced profile.

## 23. Documentation

Before release, repository documentation includes complete English and French coverage for:

- purpose and architecture boundary;
- HAOS installation and Network port configuration;
- Ingress UI;
- model configuration for both provider families;
- ACP integration;
- standalone API authentication and exact request/result/ack lifecycle;
- MCP tool descriptor contract;
- persistence/restart behavior;
- security/redaction/AppArmor boundaries;
- troubleshooting and known compatibility requirements.

The standalone API examples are directly usable and make clear that `GET` does not free the slot; `ack` does.

## 24. CI and acceptance strategy

CI must prove mechanics without requiring real paid providers:

- unit tests for persistence, state transitions, auth, priority/fallback and bounds;
- fake Ollama-compatible and OpenAI-compatible HTTP providers including tool calls, errors and structured output;
- fake Streamable HTTP MCP servers, including inventory drift and side-effect-boundary failures;
- standalone API end-to-end tests;
- ACP contract integration tests against the actual ACP contract surface or a contract-faithful fixture;
- restart recovery tests for active and pending states;
- container build/smoke tests;
- AppArmor executable-inventory validation;
- secret/redaction tests;
- bilingual/theme/version UI smoke assertions.

Real HAOS acceptance remains mandatory after each implementation lot reaches CI-conformant state.

## 25. Production-data cutoff

Development data is considered disposable only until the first release is explicitly accepted as the production baseline on the user's HAOS installation.

That acceptance establishes the Execution Plane persistence-preservation cutoff. From that point forward, schema evolution must preserve supported existing model/settings/pending state through explicit tested upgrades; clean reinstall/data deletion is no longer an ordinary migration strategy.
