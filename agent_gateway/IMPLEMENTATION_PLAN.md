# Agent Gateway — revised implementation plan

This plan replaces the original HA-MCP/Gatus-centred sequence. Agent Gateway is
a model-neutral gateway between MCP clients and any number of administrator-
configured upstream MCP servers. It acts as an application firewall for MCP
capabilities: deny by default, expose only what the administrator explicitly
authorizes, and enforce that configured capability envelope exactly. No upstream
product, task domain, tool name or model vendor is a structural dependency of the
application.

## Product model and invariants

Agent Gateway has four independent concepts:

1. **Client identities** authenticate people, agents, event sources and internal
   schedulers to Agent Gateway.
2. **MCP connectors** describe administrator-configured connections to external
   MCP servers. A connector owns its endpoint/transport, authentication material,
   health state and discovered tool catalogue.
3. **Task definitions** describe an objective and select an exact set of tools
   from one or more connectors, together with input/report schemas and execution
   limits.
4. **Jobs** are immutable executions of a task revision, claimed by authorized
   reasoning clients through leases and completed with structured reports.

The following rules apply to every phase:

- zero connectors is a valid installation state;
- no connector, including HA-MCP, is created or required by default;
- connectors are added, named, tested, enabled and removed by the administrator;
- discovery never grants execution rights;
- an upstream tool is unusable until explicitly selected in a valid task;
- a task may combine selected tools from several connectors;
- clients never receive connector endpoints, credentials or unselected tools;
- tool names are namespaced by connector identity to prevent collisions;
- authorization is deny by default and is checked again for every invocation;
- an upstream inventory is untrusted metadata, not a security classification;
- Gatus is an acceptance scenario configured by the test administrator, never a
  built-in connector, event type, task, entity list or report schema.

### Authorization model — configuration is authorization

Agent Gateway follows a deny-by-default capability model comparable to an
application firewall for MCP. Administrative configuration is the authorization
decision. A connector inventory grants no capability by itself, and a tool that
is not explicitly selected in a valid task remains unavailable to the reasoning
client.

A tool explicitly selected in a valid task is authorized for that task within
the exact envelope defined by the immutable task revision, connector and tool
fingerprint, caller authorization, effective schema and optional argument
restrictions. `fixed_arguments_v1` may further reduce that envelope by removing
administrator-fixed properties from the agent-visible schema and injecting them
server-side. Anything outside the resulting capability envelope remains
forbidden.

Agent Gateway does not infer authorization from semantic labels such as `read`,
`write`, `admin`, `safe`, `dangerous` or similar upstream descriptions. Such
labels may be useful descriptive metadata, but they neither grant nor revoke
execution rights. A write-capable tool deliberately selected by the
administrator is authorized through the same mechanism as a read-capable tool.

The gateway's security responsibility is to enforce the administrator-defined
configuration exactly and to fail closed whenever that configuration cannot be
proven applicable. It must not introduce a second authorization or mandatory
per-invocation approval layer merely because an already-authorized capability
can modify upstream state. If a task grants broader authority than intended, the
corrective action is to narrow the task, selected tools or argument surface.

## Current checkpoint

The generic gateway foundation and its main operational workflows have now
demonstrated:

- Home Assistant App installation, startup, Ingress and AppArmor operation;
- separate Ingress administration and authenticated MCP/event listeners;
- identity/credential management and gateway permissions;
- persistent events, jobs, reports and audit records;
- job leasing, heartbeat, completion and failure protocol;
- a generic administrator-managed multi-connector MCP architecture, including
  overlapping upstream tool names without collisions;
- generic task composition, virtual task capabilities and governed upstream
  invocation under an active job lease;
- generic event mappings, schedules, cooldowns and one common durable grace
  incident engine for simple and aggregated correlation;
- bounded retention, metrics and incremental audit verification whose cockpit
  reads remain O(1);
- a polished bilingual administration interface organized around an
  operational cockpit, consultation views and configuration drawers;
- a least-privilege AppArmor profile validated on HAOS through startup,
  application operation, graceful shutdown and restart;
- end-to-end Gatus/HA-MCP and generic duplicate-tool acceptance scenarios
  configured entirely through generic product concepts;
- end-to-end HAOS acceptance of `fixed_arguments_v1`, including reduced virtual
  schemas, server-side ordinary/sensitive injection, hidden-argument override
  rejection, upstream-result redaction and durable denied-invocation auditing.

Version 0.46.5 is installed and starts cleanly on a fresh HAOS App data set after
an uninstall with data removal and clean reinstall. The complete
`fixed_arguments_v1` functional recipe is accepted: ordinary and sensitive fixed
values are removed from the client-visible schema and injected server-side;
explicit overrides are rejected; sensitive values echoed by an upstream server
are redacted from both MCP `content` and `structuredContent`; rejected argument
values are never persisted; and denied invocation decisions remain durable in a
valid chained audit trail. Versions 0.46.3 and 0.46.4 closed the upstream-echo
redaction edge cases, and version 0.46.5 closed the transactional denied-audit
rollback discovered by the real HAOS recipe.

Version 0.46.6 implemented bounded connector editing and explicit connector-
secret rotation without a database-schema change. Ordinary edits never carry a
Bearer token and retain the protected secret automatically. Endpoint replacement
and explicit non-empty secret rotation rediscover the upstream inventory; a
transport or schema failure preserves the previous inventory but makes the
connector and dependent tasks fail closed; a failed rotation does not replace
the stored secret. Successful rotation replaces the copy stored and used by
Agent Gateway without claiming to revoke the old token at the upstream server.
Administration responses expose only a `has_secret`
boolean, and update/rotation audit entries contain safe metadata only.

The real HAOS 0.46.6 acceptance validated connector editing, successful and
failed secret rotation, fail-closed dependent tasks, recovery and secret
non-disclosure. It also exposed one traceability defect: endpoint changes and
secret rotations rejected while a dependent execution was active returned
`connector_execution_active` before recording the denial. Version 0.46.7
persists minimal `connectors.update` or `connectors.secret_rotate` denied audit
entries before returning that unchanged refusal, without upstream discovery,
connector mutation or requested endpoint/secret data in the audit.

The real HAOS 0.46.7 acceptance is complete. The App upgraded and started
cleanly with the existing 0.46.6 recipe data, both blocked connector mutations
continued to return `connector_execution_active`, and each refusal produced the
expected durable denied audit entry. The requested endpoint and Bearer token
were not applied or disclosed, the connector and inventory remained unchanged,
and the complete 23-entry audit chain verified successfully after the test. The
bounded connector-editing and explicit secret-rotation lot is therefore accepted
through 0.46.7.

The next release sequence is therefore:

1. finish the public-release compatibility and threat-model gates listed below.

## Phase 0 — executable security baseline (completed foundation)

Keep and continue testing:

- reproducible `amd64`/`aarch64` Home Assistant App build;
- unprivileged runtime and least-privilege AppArmor profile;
- writable paths restricted to App data and runtime temporary directories;
- separate listeners and non-sensitive liveness/readiness endpoints;
- direct initialization of the current development SQLite schema;
- redaction, correlation IDs, graceful shutdown and bilingual metadata;
- CI validation, container build and smoke tests.

## Phase 1 — authenticated durable control plane (completed foundation)

Keep and continue testing:

- independently revocable identities and one-time credentials;
- composable gateway permissions and deny-by-default enforcement;
- durable events, jobs, reports and append-oriented audit entries;
- idempotency, queue bounds, rate limits and read-only views;
- versioned MCP tools for status, permissions, events, jobs and reports;
- redacted audit export.

Event payloads and task selection must become generic during Phase 3R. Existing
Gatus literals are temporary implementation debt, not public contracts.

## Phase 2 — leases and reasoning-client protocol (completed foundation)

Keep and continue testing:

- atomic job claims and identity-bound lease tokens;
- bounded heartbeats, expiry, retries and attempt history;
- schema-validated immutable reports;
- per-identity concurrency and fair selection;
- revocation and authorization checks during active leases.

The job envelope will later expose only the namespaced tools selected by the
task revision. It must never expose an entire connector catalogue.

## Phase 3R — architectural reset to a generic gateway

Status: completed and accepted on a clean HAOS installation. No HA-MCP server,
Gatus source, event type, task or tool is seeded or required by the product.

Deliverables:

- remove all hard-coded Gatus event types, source names, requested task names,
  task seeds, entity assumptions and fixed report validation;
- remove `ha_mcp_url` and HA-MCP-specific status from fixed App configuration;
- replace the singular HA-MCP adapter with generic connector abstractions;
- define persisted connector, connector-secret, inventory-snapshot and tool
  descriptor models without introducing a migration framework;
- define connector lifecycle states such as `unconfigured`, `checking`,
  `ready`, `unreachable`, `inventory_changed`, `disabled` and `invalid`;
- update the UI language and APIs so the product contains no implicit upstream
  connector;
- retain the present HA-MCP code only where it can become transport-neutral MCP
  client code; delete special-case behavior instead of wrapping it indefinitely;
- replace the original ADR assumptions with a generic multi-connector design
  decision before connector execution is implemented.

Acceptance criteria:

- a clean installation starts and is ready with zero connectors;
- no source file or database seed defines a Gatus task or HA-MCP dependency;
- control-plane tests use neutral example task/event names;
- connector secrets remain excluded from logs, reports, exports and MCP output;
- the existing identity, queue, lease, report and audit suites still pass.

This phase requires an announced App uninstall with data removal and clean
reinstall because the development database contains no useful user data.

## Phase 4 — administrator-managed MCP connectors

Status: lifecycle implementation completed and accepted on HAOS through 0.46.7.
The full editing and rotation recipe passed on 0.46.6, and the denied-audit
traceability patch passed its focused HAOS acceptance on 0.46.7. Generic HA-MCP
and fake MCP servers have been added through the same interface, and duplicate
upstream tool names have been exercised without collision. Connector creation,
checking, enable/disable, archival, inventory discovery and safe secret
persistence are implemented. Bounded connector editing and explicit credential
rotation are implemented without exposing an existing endpoint path/query or
Bearer token.

Deliverables:

- Ingress workflow to add, edit, test, enable, disable and remove MCP connectors;
- user-defined connector display name and stable internal identifier;
- supported MCP transport configuration, endpoint validation and bounded
  administrator-supplied authentication settings;
- encrypted/private connector-secret storage with one-time input and rotation;
- MCP initialization, health check and tool discovery with strict timeouts,
  response-size limits and normalized failures;
- stored inventory snapshots containing tool name, description, input schema and
  a canonical schema fingerprint;
- namespaced display of tools as `<connector>.<tool>`;
- connector detail UI with health, last successful check, inventory revision and
  explicit refresh;
- no connector-specific fields or HA-MCP branding in the core model/API.

Validity checks:

- a connector cannot become `ready` until configuration validation, MCP
  initialization and tool discovery all succeed;
- duplicate names are either rejected or disambiguated without changing stable
  IDs;
- arbitrary request/job input can never override a connector endpoint;
- loopback/private-network policy is administrator-controlled but SSRF-safe;
- discovery failure preserves the last inventory for inspection but marks it
  stale and prevents new task activation until reconciled;
- tool additions grant nothing; removals or schema changes invalidate affected
  task revisions rather than silently broadening or altering them;
- deleting a connector is blocked while active task revisions reference it;
- an unavailable connector cannot expose credentials or raw protocol errors.

Acceptance criteria:

- zero, one and several connectors are supported without special cases;
- two connectors may expose the same upstream tool name without collision;
- a generic test MCP server can be added without changing Agent Gateway code;
- HA-MCP can be added through the same UI as that generic server, but is not
  required for any App health state unrelated to its own connector;
- a tool catalogue is visible to administrators but invisible to normal clients.

## Phase 5 — configurable task composer

Status: completed and accepted on HAOS for the current selected scope. Version
0.46.0 adds the complete persisted `fixed_arguments_v1` path and its collapsed
editor; versions 0.46.1 and 0.46.2 harden upstream-schema enforcement and make
schema rejections operationally visible. Versions 0.46.3 and 0.46.4 close
sensitive upstream-echo redaction edge cases, and version 0.46.5 makes denied
capability-invocation audit decisions durable before their normalized error is
returned. The real HAOS recipe has accepted ordinary and sensitive fixed-value
injection, virtual-schema removal, override rejection, response redaction, audit
non-disclosure and audit-chain integrity. Administrator-defined task
input/report schemas, detailed timeouts and per-task identity bindings from the
broader original deliverable remain future extensions, not unresolved
acceptance items for the current scope.

Deliverables:

- Ingress workflow to create a task with name, objective/instructions, input
  schema, report schema, timeouts, attempts and execution limits;
- connector/tool picker supporting one or more tools from one or more ready
  connectors;
- two argument-exposure modes per selected tool: `standard`, which preserves
  the upstream input schema unchanged, and optional `fixed_arguments_v1`, which
  hides and injects administrator-defined fixed top-level arguments;
- immutable task revisions containing connector IDs, inventory fingerprints,
  exact tool descriptors, argument-exposure mode and report contract;
- task states `ready`, `unavailable`, `disabled` and `retired`; an incomplete
  composition remains local to the form and is not persisted as a task;
- dependency view explaining exactly why a task is or is not executable;
- authorization bindings controlling which identities may create jobs, claim
  the task, invoke its selected tools and read its reports.

Validity checks:

- a task cannot be created without at least one selected tool from a ready,
  enabled connector;
- every selected tool must exist in the connector's current inventory and match
  the fingerprint captured by the task revision;
- a task referencing a disabled, deleted, unreachable-without-valid-snapshot or
  changed connector becomes unavailable and cannot create new jobs;
- in `standard` mode, the selected tool exposes its upstream input schema
  unchanged;
- in `fixed_arguments_v1` mode, fixed top-level properties are absent from the
  virtual schema and are injected by the gateway after validating the arguments
  visible to the agent;
- no task can select connector administration, secret or raw passthrough
  operations supplied by Agent Gateway itself;
- task readiness is enforced by the application service and database
  transaction, not only by disabled buttons in the browser.

Acceptance criteria:

- an administrator can compose one task from tools on two unrelated MCP
  connectors without editing YAML or Python;
- removing a selected tool makes the dependency failure visible and blocks new
  execution;
- reconnecting and explicitly reconciling an unchanged tool safely restores the
  task;
- clients see only the task objective, permitted namespaced tools, their
  effective virtual schemas and the report schema.

### Selected design — optional fixed-argument tool restrictions

The earlier generic per-field policy-editor direction is abandoned. Agent
Gateway implements only one deliberately small, generic restriction mechanism:

- `standard` remains the default and exposes the selected upstream tool schema
  unchanged;
- optional `fixed_arguments_v1` starts from one administrator-supplied valid
  example call;
- for each top-level property present in that call, the administrator chooses
  either editable by the agent or fixed by the gateway;
- fixed properties disappear entirely from the virtual MCP tool schema;
- optional properties absent from the example and not editable also disappear
  and are not injected;
- arguments submitted by the agent are first validated against the reduced
  schema with unknown properties rejected;
- the gateway then injects fixed values, validates the merged object against
  the immutable upstream schema snapshot, and only then invokes the exact
  connector tool selected by the task revision;
- fixed values always win structurally: an agent attempt to submit a hidden
  property is rejected, never silently overwritten;
- restrictions are stored per tool selection and task revision, remain
  independent for tools with identical names on different connectors, and fail
  closed when the upstream schema fingerprint changes;
- every fixed argument is explicitly classified as either `ordinary` or
  `sensitive`. This confidentiality classification is independent from the
  capability restriction: both kinds disappear from the agent-visible schema
  and remain impossible for the agent to override;
- ordinary fixed values remain visible to administrators in task details and
  bounded administrative audit views, so the effective capability can be
  reviewed in a form such as
  `ha_addon(addon="gatus", action=<agent>)`; they remain absent from the MCP
  schema exposed to the agent;
- sensitive fixed values reuse the connector-secret protection primitive at
  rest and are always redacted from MCP output, logs, reports, errors and audit
  metadata. Administrative views show only that a protected value is fixed;
- the task composer requires an explicit confidentiality choice when a value is
  fixed and must never infer that every fixed value is a secret merely because
  it restricts the capability;
- the first version supports only whole top-level properties. Nested partial
  locking, regexes, numeric ranges, ACLs, transformations, conditional rules
  and a policy DSL are explicitly out of scope.

The Ingress task composer keeps these controls collapsed by default. When the
mode is enabled, it generates a form from the upstream input schema, validates
the example call, and offers `Editable by agent`, `Fixed ordinary value` or
`Fixed sensitive value` for each applicable top-level property. The mechanism
remains connector- and domain-agnostic: it can, for example, remove an `addon`
argument from the virtual surface and inject `addon="gatus"` without Agent
Gateway knowing what Home Assistant or Gatus are.

## Phase 6 — governed connector invocation

Status: implemented and accepted on HAOS for both standard capabilities and
`fixed_arguments_v1`, including one task combining identically named tools from
two independent connectors. The real fixed-argument recipe confirms reduced
client-visible schemas, server-side fixed-value injection, rejection of hidden
ordinary and sensitive overrides, value-aware redaction of sensitive upstream
echoes from both MCP result representations, and durable denied-invocation audit
entries that never persist rejected argument values.

Deliverables:

- a versioned gateway MCP operation for invoking a task-selected capability
  under an active job lease;
- exact lookup by task revision, connector ID, tool name and schema fingerprint;
- server-side validation against the effective virtual schema, fixed-argument
  injection when enabled, then validation against the captured upstream schema;
- bounded upstream calls, cancellation, normalized content, response limits and
  secret redaction;
- invocation audit recording identity, job, task revision, connector, tool,
  decision, duration and redacted outcome;
- bounded per-job invocation count and per-connector concurrency;
- clear transient/permanent failure classification without leaking upstream
  credentials or stack traces.

Acceptance criteria:

- a leased client cannot invoke an unselected connector or tool;
- it cannot submit hidden fixed arguments, invoke an argument outside the
  effective schema or reuse the lease for another job;
- connector inventory changes fail closed until administrator reconciliation;
- connector credentials never cross the Agent Gateway boundary;
- failures on one connector do not corrupt the job or other connector state;
- write/admin-labelled tools receive neither automatic permission nor automatic
  prohibition merely because of their semantic label: execution rights come
  only from explicit task selection and caller authorization, under the same
  schema, fingerprint, lease and argument checks as any other selected tool.

## Phase 7 — first real acceptance workflow

Status: completed and accepted on HAOS for both the standard capability path and
the optional `fixed_arguments_v1` path. Gatus/HA-MCP diagnosis, job leasing,
virtual tool invocation, structured report persistence and audit visibility have
passed end-to-end acceptance. The generic fake MCP multi-connector scenario has
also passed. The fixed-argument extension has additionally passed ordinary and
sensitive injection, override-rejection, response-redaction and durable-audit
acceptance on real HAOS.

The first end-to-end test may use an existing Gatus deployment and HA-MCP, but
everything is configured through the generic UI:

1. add HA-MCP as an ordinary MCP connector;
2. verify and inspect its discovered inventory;
3. create a `Diagnostic incident Gatus` task;
4. select the exact HA tools needed by that diagnostic task; this particular
   acceptance scenario may use read-only tools, but read-only is not an Agent
   Gateway authorization class;
5. optionally fix only the few top-level arguments that must never be chosen by
   the agent, when the upstream schema makes this possible;
6. create a client identity allowed to claim that task;
7. enqueue a manual test job, complete it and inspect its report/audit trail.

Acceptance criteria:

- the implementation contains no Gatus identifier or HA-MCP special case;
- another administrator can reproduce the same mechanics with unrelated MCP
  servers, tools and task names;
- the selected tool set can vary as upstream inventories change;
- no capability outside the explicit task selection can be invoked; a selected
  write-capable tool is governed by the same rules as any other selected tool;
- the full job, capability and report trail is understandable from the UI.

Persistent identities, task definitions and jobs become non-disposable only
when an explicit testing or user-retention phase begins. Until then the clean
schema policy below applies even though the manual workflow is functional.

## Phase 8 — generic triggers and schedules

Status: completed for the selected generic scope and accepted on HAOS, including
the real Home Assistant automation forwarding strict state transitions from 15
ICMP probes. Version 0.28.0 introduces persistent interval schedules, their
bounded single-instance dispatcher and Ingress lifecycle controls. Event source
mappings arrive in version 0.29.0: an administrator binds an exact authenticated
source identity and event type to one ready task, and sources can no longer
select arbitrary tasks in event payloads. Version 0.30.0 adds bounded per-mapping
cooldowns and suppresses duplicate jobs while retaining and auditing every
authenticated event. Version 0.31.0 adds a guarded dead-letter relaunch that
creates a fresh job without rewriting the failed execution or its attempts.
Version 0.32.0 adds execution-health counters and operational filters so active
work and dead letters remain immediately visible without changing persistence.
Version 0.33.0 adds the first bounded declarative input transformation: a
mapping can forward the complete event, only its subject, or only its attributes
while the complete authenticated event remains retained for audit.
Version 0.34.0 adds durable grace windows paired with an administrator-defined
recovery event type. Pending windows survive restarts, repeated alerts do not
extend them, and a recovery cancels them before the bounded dispatcher queues
the task. Version 0.35.0 adds editable triggers and schedules plus daily and
weekly calendar schedules in an explicit IANA timezone. Their next occurrence
is recalculated after edits and resumes, while missed occurrences are never
replayed in a burst. Version 0.41.0 replaces the single pending grace window
with the common durable incident engine described below. It supports both the
compatible simple mode and bounded aggregation by stable subject, including
atomic promotion, explicit blocked state and administrator retry.

Deliverables:

- authenticated generic event sources and configurable event-to-task mappings;
- mapping-level input transformation with bounded declarative rules, never code;
- recurring schedules referencing an immutable ready task revision;
- idempotency, grace/cooldown rules, rate limits, queue quotas and overload
  handling shared by manual, event and scheduled jobs;
- operational UI for sources, mappings, schedules and dead letters;
- optional notification connector/tool selected through the same
  task/capability model, with fixed top-level arguments only when explicitly
  configured.

Validity checks:

- an event source cannot choose an arbitrary task outside its configured
  mapping;
- mappings and schedules cannot activate against unavailable tasks;
- a task becoming unavailable suspends dependent triggers visibly and safely;
- adding a source grants no connector execution rights;
- restart misfires, DST changes and event storms remain deterministic and
  bounded.

The Gatus Home Assistant automation becomes documentation for one possible
configuration, not an application contract.

### Selected evolution — durable multi-subject grace incidents

The current one-pending-window-per-mapping behavior remains correct for simple
sources but cannot safely correlate several simultaneously failing subjects: a
recovery for one subject can cancel work still required for another. Grace
handling will therefore use one common durable incident engine with two
administrator-visible correlation modes:

- `simple` preserves mapping-level behavior through one synthetic incident
  member;
- `aggregate_by_subject` derives a stable subject key from SHA-256 of the
  canonical subject JSON and tracks each active subject independently inside
  one incident per mapping.

These are two correlation modes over the same incident lifecycle, persistence
model and dispatcher, not separate grace engines. In aggregated mode a
non-empty subject is mandatory. The source contract must treat `subject` as
stable resource identity and place changing observations in `attributes`.

Durable representation:

- one pending incident records its mapping, captured task and authorization
  revisions, opening time, immutable grace deadline and promotion state;
- bounded incident-member rows record the correlation key, canonical subject,
  first and latest alert event references, latest transformed input and
  observation timestamps;
- all alert and recovery events remain individual immutable event-history and
  audit entries regardless of whether a job is eventually created;
- the number of active subjects and canonical byte size of each subject and of
  the aggregate input have explicit hard limits. Boundary overflow fails
  closed, remains audited and cannot silently discard an existing member.

Lifecycle rules:

- the first alert opens the incident and fixes its deadline; later alerts never
  extend it;
- a new subject adds one member, while a repeated alert for the same subject
  updates its latest event/input without creating a duplicate;
- a matching recovery removes only that member; recovery of an unknown subject
  is a successful no-op with an explicit audit outcome;
- removing the last active member closes the pending incident without a job;
- a subject recovered and alerted again before expiry rejoins the same pending
  incident;
- expiry creates at most one job containing all subjects still active; a later
  recovery is retained but never mutates or cancels that job;
- cooldown begins only after actual job creation and never suppresses member
  updates inside an already open incident;
- idempotent HTTP replay never mutates incident membership twice;
- ingestion, recovery and due promotion use atomic transactions. Concurrency
  tests must cover simultaneous alerts for equal and different subjects,
  alert/recovery races and recovery/promotion races, proving that no member is
  lost and no duplicate job is created;
- an expired incident that cannot be promoted because of readiness, active-job,
  queue or cooldown protection remains visible with its blocking reason.
  Promotion work and automatic retries are bounded; exhaustion moves the
  incident to an explicit administratively actionable state, never silent
  deletion or an infinite hot retry loop.

Aggregated jobs use a versioned deterministic envelope rather than pretending
to be one source event. It contains the event type, incident timestamps and a
list sorted by subject key. Every member always retains its subject identity;
the mapping's existing input mode determines its associated data:

- `full_event` supplies the latest complete alert event for each member;
- `subject` supplies the subject without duplicate associated data;
- `attributes` supplies the subject plus the latest attributes.

The simple mode is emitted through the same envelope-building path with one
member wherever compatibility permits. Existing queue bounds, task readiness,
tool fingerprints, cooldown, retention and audit invariants continue to apply.
The SQLite schema is replaced directly for this evolution; no migration or
legacy compatibility path is implemented. Acceptance uses an App uninstall
with data removal followed by a clean reinstall. Schema, dispatcher behavior,
UI status and tests are delivered together in version 0.41.0 before the
administration-interface restructuring.

## Phase 9 — security hardening and release readiness

Status: the hardening foundation is substantially completed. Retention, bounded
metrics, append-oriented audit verification, strict upstream JSON Schema
enforcement, secret redaction and fail-closed connector behavior are implemented.
The AppArmor least-privilege audit is also completed and accepted on HAOS: the
bounded diagnostic campaign derived the runtime allowlist from real startup,
operation, restart and shutdown traces; broad executable-tree and persistent-data
rules were removed; enforcement was restored; and CI now prevents those broad
rules from returning. AppArmor is therefore a non-regression requirement, not a
remaining implementation phase.

Version 0.36.0 introduces bounded operational-data retention, manual preview and
cleanup, optional daily cleanup, and complete audit-chain verification. Version
0.37.0 adds reversible task and connector archival, preserves their complete
history, and commits the duplicate-tool fake MCP used by the multi-connector
acceptance test. Version 0.38.0 adds bounded operational metrics and completes
the French/English interface and operator documentation. Versions 0.39.0 through
0.40.7 complete the bounded HAOS AppArmor audit and its CI non-regression
guards. Audit entries remain append-only and are deliberately excluded from
retention. Version 0.45.0 moves complete chain traversal out of cockpit and
retention request paths, persists the last valid checkpoint separately from
transient verification state, revalidates the HMAC anchor before bounded
incremental verification, and falls back to a complete verification on any
inconsistency without replacing the last valid checkpoint after failure.
Complete verification runs at startup, every 24 hours and on explicit
administrator request. This operational checkpoint is not a new root of trust
and does not authorize audit truncation; archival must still be designed before
any truncation is allowed. Version 0.45.1 keeps a confirmed invalid state
quiescent during ordinary 60-second worker passes; only startup, an explicit
request, the 24-hour deadline or an interrupted `verifying` state can schedule
another complete traversal. Version 0.46.1 enforces the complete admitted
upstream JSON Schema before every invocation. Version 0.46.2 preserves
schema-rejection causes across connector creation, refresh and reactivation:
reachable incompatible connectors become `invalid` with a precise
`last_error_code`, transport failures remain `unreachable`, safe warning logs
carry no schema or secret, and the bilingual connector UI exposes both an
administrator explanation and the machine code. Version 0.46.3 adds
invocation-scoped value-aware redaction for sensitive fixed values echoed by an
upstream server, including nested and substring appearances, while keeping
ordinary fixed values observable. Version 0.46.4 extends the same protection to
textual keys contained inside sensitive fixed JSON objects. Version 0.46.5 makes
`invalid_capability_arguments` and `capability_not_available` denial audits
durable by committing them before the normalized error escapes the transaction;
rejected arguments are never written to audit metadata and the chained audit
remains valid. The complete fixed-argument path through 0.46.5 has passed its
real HAOS recipe and a subsequent clean-install startup acceptance. Version
0.46.7 closes the remaining connector-mutation traceability gap by persisting
minimal denied audit entries for active-execution endpoint changes and secret
rotations before returning `connector_execution_active`. Its focused HAOS
acceptance confirms both denials are durable, contain no requested endpoint or
secret data, cause no connector mutation or upstream rediscovery, and preserve
a valid complete audit chain.

Keep and complete:

- retention, bounded pruning, audit-chain verification and recovery tooling;
- metrics without secrets or high-cardinality sensitive fields;
- the already accepted least-privilege AppArmor profile, with existing CI
  invariants preventing complain mode, broad executable-tree access, broad
  persistent-data access and unexpected s6/runtime drift from silently becoming
  normal policy;
- a new AppArmor trace or HAOS audit only when a legitimate runtime/base-image
  change actually requires additional permissions, not as a standing release
  milestone and never because a selected MCP tool is semantically labelled
  `write`;
- strict fail-closed enforcement of exact task revision, connector, tool,
  fingerprint, caller authorization, effective schema and optional fixed
  arguments for every invocation;
- secret protection and redaction across connector storage, MCP output, logs,
  reports, errors and audit metadata;
- additional transports/connectors only through the generic connector contract;
- a future schema-upgrade policy only after real non-disposable user data exists
  and preserving it becomes an explicit requirement.

Write-capable, corrective or administratively powerful upstream tools are not a
separate authorization class and are not deferred merely because they can modify
state. When the administrator explicitly selects such a tool in a valid task and
the caller is authorized for that task, it belongs to the configured capability
envelope and is governed by the same deny-by-default, exact-selection, schema,
fingerprint, lease, argument-restriction, redaction and audit guarantees as any
other tool. Unselected, implicitly granted, unrestricted or raw-passthrough
capabilities remain forbidden. Security review verifies enforcement of this
existing model; it does not add a second authorization engine.

### Administration interface information architecture review

Before adding further configuration density, review the complete Ingress
interface. The current pages often mix three different concerns in the same
view: resource configuration, live operational state and historical data. This
makes the interface increasingly difficult to scan even though each individual
control remains understandable.

The redesign must establish a consistent structure across identities,
connectors, tasks, triggers, schedules, executions, reports and audit:

- use a deliberate two-row header: a stable brand/version row with language and
  theme controls, followed by a dedicated navigation row;
- use nearly all available desktop Ingress width with bounded page padding and
  a generous maximum width; on narrower screens keep navigation on one line
  with horizontal scrolling instead of compressing or accidentally wrapping;
- make Overview a read-only operational cockpit whose accessible linked cards
  summarize ready/unavailable connectors and tasks, active identities,
  triggers, grace incidents, schedules, 24-hour events and reports, queued and
  leased jobs, dead letters and audit-chain validity;
- extend the existing bounded status endpoint for missing dashboard aggregates
  instead of issuing one browser request per resource; distinguish actual
  failures from deliberately disabled or archived resources;
- create a dedicated top-level Identities page and remove identity creation and
  administration from Overview;
- separate creation and editing workflows from operational lists and history;
- replace permanent left-column forms for identities, tasks, triggers,
  schedules and connectors with consistent page actions and a reusable right
  drawer; move retention configuration into the same mechanism;
- give the drawer dialog semantics, labelled title, overlay, Escape handling,
  focus capture/restoration, background-scroll prevention and a mobile
  full-width layout without adding a heavy frontend framework;
- prevent accidental dismissal of the one-shot identity credential until the
  administrator explicitly acknowledges copying it or confirms its loss;
- keep Events, Executions and Reports as full-width consultation views and keep
  Audit primarily consultative with chain status, cleanup preview and journal
  visible outside its retention drawer;
- distinguish configuration state from health, readiness and recent activity;
- provide compact list views with deliberate detail/edit screens or panels;
- keep destructive and lifecycle actions grouped and visually distinct;
- preserve the current bilingual behavior, Ingress navigation, dark theme and
  responsive layout;
- avoid exposing internal identifiers or raw JSON in primary workflows when a
  human-readable representation exists;
- design the optional fixed-argument editor as part of the task detail/edit
  workflow rather than adding more permanent density to the task list page.

Start with an inventory and wireframe-level proposal before changing code, then
implement the redesign in grouped releases to limit HAOS install/test cycles.
The implementation order used for this redesign was: multi-subject incident
correctness first; shared header/drawer/navigation foundations and the Identities
page second; Overview and remaining page moves third; and the optional
fixed-argument editor in the new wide task drawer fourth. Tool authorization
remains generic and is never gated merely by a semantic read/write label.

The shared header, reusable accessible drawer and dedicated Identities page are
delivered together in version 0.42.0.

The read-only operational cockpit and the remaining configuration-form moves
are delivered together in version 0.43.0.

The complete optional `fixed_arguments_v1` path and its collapsed editor in the
wide task drawer are delivered together in version 0.46.0. Standard exposure
remains the default; restricted selections persist reduced schemas, inject and
revalidate fixed values, and protect sensitive values without a database
migration or a second policy mechanism.
Version 0.46.1 closes the upstream-schema validation gap: admitted MCP schemas
use Draft 2020-12 with known keywords, known formats and local references only,
and the complete schema is enforced before every upstream invocation in both
standard and `fixed_arguments_v1` modes.
Version 0.46.2 exposes every admitted schema-rejection category from discovery
through persistent connector state, administration APIs, safe logs and the
bilingual connector cards without weakening fail-closed validation. Version
0.46.3 redacts invocation-scoped sensitive fixed values when an upstream server
echoes them through otherwise neutral result fields; version 0.46.4 extends that
protection to textual keys inside sensitive fixed JSON objects. Version 0.46.5
persists denied capability-invocation audit decisions before returning
`invalid_capability_arguments` or `capability_not_available`, without storing
rejected argument values. The complete `fixed_arguments_v1` path has now passed
HAOS installation, startup, positive invocation, ordinary/sensitive override
rejection, result-redaction, persistent-audit and audit-chain acceptance,
followed by a clean data-removal reinstall of 0.46.5.

## Release gates

Before a public release, the repository must also contain:

- bilingual README, documentation, changelog and App translations;
- operator documentation for connector creation, secret rotation, task
  composition, client identity setup, network exposure, backup and recovery;
- a compatibility statement listing supported MCP transports/protocol versions;
- a threat-model matrix connecting every boundary to automated or documented
  manual verification and treating explicit administrator configuration as the
  source of capability authorization;
- tests using at least two independent fake MCP servers and overlapping tool
  names;
- proof that no connector, vendor, task domain or write capability is enabled by
  default;
- proof that every executable upstream capability can be traced to an explicit
  administrator-selected task/tool configuration, and that invocation fails
  closed when no such configuration exists.

## Schema policy during the current development stage

Agent Gateway currently has no users and its sole test installation contains no
data that must survive a schema change. During this stage, schema-breaking
functional increments replace the fresh SQLite schema directly and require an
App uninstall with data removal followed by a clean reinstall. They must not
ship migrations, legacy compatibility branches, Alembic, SQLAlchemy or another
upgrade framework merely to preserve disposable development data.

An existing database with an incompatible schema continues to fail closed with
a clear clean-reinstall instruction; it is never altered partially or accepted
silently. A data-preserving upgrade policy will be designed only when real
non-disposable test or user data exists and preservation becomes an explicit
requirement.

## Deferred by design

The following require an explicit later decision or ADR:

- unconstrained, implicitly granted or raw-passthrough write capabilities outside
  the explicit connector/tool/task/schema model;
- raw arbitrary shell, SSH, Git-write or network-wide administration interfaces
  that bypass the explicit connector/tool/task/schema model;
- transparent exposure of an entire connector inventory to clients;
- automatic trust in upstream tool descriptions or names;
- embedded models, chat UI, memory system or model-vendor authentication;
- multi-instance/high-availability deployment;
- making Agent Gateway an OAuth authorization server;
- configuration export/import, because Home Assistant backups already provide
  coherent App restoration; portable templates can be reconsidered only after
  a concrete cross-installation use case exists.

### Future reasoning worker authentication

Do not assume that an independently developed reasoning worker necessarily
requires a separately billed model API key. The worker/provider layer must be
designed with pluggable authentication and, where the selected provider and
runtime officially support it, offer both:

- direct API-key authentication with provider usage-based billing; and
- subscription authentication through the provider's supported OAuth flow.

OpenClaw is the reference interoperability example: its OpenAI provider can use
either an OpenAI Platform API-key profile or ChatGPT/Codex OAuth subscription
authentication. This choice belongs to the reasoning worker, not to Agent
Gateway. Agent Gateway remains model-neutral, exposes its governed MCP surface
to the worker and must not receive, store or proxy the worker's model-provider
credentials.

OAuth subscription access must not be treated as a universal replacement for
the provider API. Available models, quotas and auxiliary features depend on the
live subscription catalogue and provider rules; capabilities requiring direct
Platform billing may still require an API key. A future embedded or companion
worker decision must therefore evaluate both modes explicitly instead of
declaring API-key billing mandatory by default.