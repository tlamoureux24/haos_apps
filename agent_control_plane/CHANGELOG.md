# Changelog

## 1.1.10

- Replace expected external-certificate tracebacks with one concise English
  listener-containment error containing the underlying cause.

## 1.1.9

- Report certificate fingerprint mismatches precisely when checking,
  re-enabling, or rotating credentials for an existing MCP connector.

## 1.1.8

- Preserve the active MCP connector configuration when an edited certificate
  fingerprint is rejected, and return the precise bilingual mismatch error.

## 1.1.7

- Reject mismatched pinned MCP certificates with one safe English diagnostic
  and a precise bilingual UI error, without leaking SDK exception groups.

## 1.1.6

- Keep CSRF protection functional when Home Assistant Ingress is opened over
  HTTP, while retaining Secure cookies for browser-facing HTTPS Ingress.

## 1.1.5

- Restrict the Home Assistant App to AMD64 only.

## 1.1.4

- Harmonize the neutral certificate-regeneration button with Agent Execution Plane.

## 1.1.3

- Support both legacy and current `cryptography` certificate-validity APIs so
  TLS validation is identical in GitHub CI and the HAOS image.
- Keep lifecycle, schedule, retention and audit maintenance workers exclusively
  in the Ingress administration process after splitting event and MCP ports.

## 1.1.2

- Report a degraded service when an invalid HTTPS certificate prevents a
  public listener from starting.
- Show listener state on Transport & TLS and make certificate regeneration a
  neutral, explicitly confirmed action.

## 1.1.1

- Standardize MCP on port `8098` and move event intake to `8100`.
- Move certificate controls to a dedicated Transport & TLS page and correct
  translated Home Assistant network descriptions.

## 1.1.0

- Split event intake (`8100`) from MCP/worker traffic (`8098`), add independent
  HTTP/HTTPS choices, persistent self-generated or external certificates, and
  SHA-256 certificate pinning for outbound MCP connectors.
- Keep Ingress administration available when a public certificate is invalid,
  expose certificate status/regeneration, and warn whenever HTTP is selected.

## 1.0.2

- Correct the worker setup guide: ACP workers use an identity of type MCP
  client; the four job lifecycle permissions define its worker role.

## 1.0.1

- Expand the French and English operator guides with current Activity,
  connector-maintenance, fixed-argument JSON, AEP worker, and transport-security
  workflows.

## 1.0.0

- Promote the already stable Home Assistant App to the 1.0 production version
  after its governance, orchestration, audit and ACP↔AEP boundary paths passed
  real-HAOS acceptance.
- Preserve every API, MCP, storage, policy and execution contract unchanged.

## 0.46.13

- Add a persistent, payload-free Activity view backed by the existing audit
  chain, including normal administration, orchestration and security actions.
- Record and translate `app_started`, `app_ready` and `app_stopped` lifecycle
  markers without introducing a second operational data store.
- Reorder navigation to Overview, Activity, Connectors, then Identities so MCP
  configuration is grouped before governance and execution views.

## 0.46.12

- Drive the Overview service badge from the real `/admin/api/v1/status`
  response instead of rendering an unconditional success label.
- Show a bilingual red unavailable state when the administration status probe
  fails or does not report `ready`, while retaining `/health/ready` for HAOS.
- Align the Ingress smoke test with the dynamic badge while preserving the
  independent technical readiness probe.

## 0.46.11

- Allow revoked identities to be archived without deleting credentials, policy
  bindings, jobs or audit history; active identities are rejected server-side.
- Hide archived identities by default and add the same explicit archived-items
  filter used by tasks, without any restore or reactivation action.
- Persist the presentation-only archive timestamp in existing durable metadata
  so installed databases require no migration or reset.

## 0.46.10

- Define report `findings` as an array of strings in the generated task result
  schema, matching the documented ACP report contract and making that schema
  admissible as a Codex/OpenAI structured output.
- Regression-test the exact report schema delivered to an AEP worker so a task
  can reach its permitted dynamic tool instead of failing early with
  `provider_failure`.

## 0.46.9

- Make `jobs_fail_v1` idempotent with a caller-supplied completion key, matching successful completion delivery and making retries safe after a lost response.
- Publish and regression-test the updated lifecycle tool schema used by Agent Execution Plane workers without changing ACP governance or connector behavior.

## 0.46.8

- Finalize the pre-production product and Home Assistant App identity as Agent Control Plane before persistent production configuration begins; no user-data migration is required at this cutoff.
- Refresh each administration view immediately on navigation using only its
  targeted data loader.
- Poll only the active operational view at bounded intervals, with suspension
  for hidden browser tabs, open administration drawers and expanded details.
- Display a bilingual, per-view age for the last successful refresh on the
  overview, events, executions, reports and audit views.

## 0.46.7

- Persist safe denied audit entries when connector endpoint changes or secret
  rotations are rejected because a dependent execution is active.
- Keep the refusal ahead of upstream discovery and connector mutation without
  recording the requested endpoint, Bearer token or administrative payload.

## 0.46.6

- Add bounded editing of connector display names and optional endpoint
  replacement without ever returning the protected endpoint or Bearer token.
- Preserve the existing Bearer token during ordinary edits and provide a
  separate explicit action to configure or rotate it.
- Rediscover connectors after endpoint replacement or secret rotation, retain
  the previous inventory on failure and make dependent tasks fail closed until
  their exact tool fingerprints are available again.
- Audit connector updates and secret rotations using safe metadata only, and
  expose only whether a connector currently has a configured secret.

## 0.46.5

- Commit denied capability-invocation audit entries before returning
  `invalid_capability_arguments` or `capability_not_available` to the client.
- Keep rejected arguments and sensitive fixed values out of durable audit
  metadata while preserving a valid chained audit trail.

## 0.46.4

- Treat textual keys inside a sensitive fixed JSON object as transient
  sensitive candidates when redacting upstream MCP results.

## 0.46.3

- Redact every transient `fixed_sensitive` value recursively from upstream MCP
  results, including nested innocent keys, structured content and substrings.
- Preserve ordinary fixed values and standard tool behavior while keeping the
  existing key-name and credential redaction protections.
- Promote Agent Control Plane metadata and active French/English documentation from
  experimental to stable.

## 0.46.2

- Preserve fail-closed MCP schema rejection causes across connector creation,
  refresh and reactivation instead of reporting them as network failures.
- Mark reachable connectors with inadmissible schemas as `invalid`, retain the
  precise machine code in `last_error_code` and log only safe diagnostic
  context.
- Show a bilingual administrator-facing explanation and technical error code
  directly on unavailable connector cards and during connector creation.

## 0.46.1

- Enforce admitted MCP input schemas with the Draft 2020-12 reference
  validator before discovery, task composition and every upstream invocation.
- Apply `enum`, `const`, numeric bounds, `pattern`, formats, compositions,
  object and array constraints in both standard and fixed-argument modes.
- Reject invalid schemas, unknown keywords, unsupported dialects or formats,
  external references and oversized schemas explicitly instead of ignoring or
  truncating their constraints.

## 0.46.0

- Add optional `fixed_arguments_v1` restrictions to each selected task tool:
  agent-editable top-level properties remain visible while ordinary and
  sensitive fixed properties disappear from the virtual MCP schema.
- Validate an administrator example call, persist restrictions per immutable
  task revision, inject fixed values server-side and validate the merged call
  again before invoking the exact upstream tool.
- Protect sensitive fixed values at rest with the existing private encryption
  primitive and redact them from administrative details and audit output while
  keeping ordinary fixed values inspectable.
- Add the collapsed bilingual fixed-argument editor to the existing wide task
  drawer and show each configured effective capability in the task list.

## 0.45.2

- Reserve a stable root scrollbar gutter so taller administration views no
  longer shift the header and content horizontally.

## 0.45.1

- Keep a confirmed invalid audit state stable during ordinary 60-second worker
  passes instead of repeating an unbounded full-chain scan every minute.
- Retry a full verification only on administration startup, explicit manual
  request, the 24-hour deadline, or recovery from an interrupted `verifying`
  state.

## 0.45.0

- Make cockpit and retention audit health reads strictly bounded: neither
  request path traverses or recalculates the audit chain.
- Persist the last valid audit checkpoint separately from transient
  verification state, revalidate its HMAC anchor before every incremental
  advance and verify new entries in bounded batches.
- Fall back immediately to a full verification when a checkpoint, anchor or
  suffix is inconsistent, while preserving the last valid checkpoint until a
  complete verification succeeds.
- Run full verification outside page loads at administration startup, every
  24 hours and on explicit administrator request; expose valid, pending,
  verifying, unverified and invalid states in the bilingual interface.

## 0.44.0

- Add timezone-aware ISO timestamps to Agent Control Plane launcher messages and to
  both Uvicorn listeners without widening the minimal AppArmor profile.

## 0.43.0

- Turn Overview into a read-only operational cockpit with linked cards for
  connectors, tasks, identities, triggers, schedules, recent events and
  reports, active jobs, grace incidents, dead letters and audit-chain health.
- Extend the single bounded administration status response with dashboard
  aggregates that distinguish unavailable resources from deliberately
  disabled or archived ones.
- Move task composition, connector creation, trigger and schedule creation or
  editing, and retention configuration into the reusable administration
  drawer; keep their resource lists and operational state full width.
- Add a wider responsive drawer variant for task and trigger workflows and
  close configuration drawers after successful submission.
- Show human task names and a human-readable event association in primary
  execution and report tables instead of internal slugs and UUIDs.
- Preserve the bilingual, dark-theme and narrow-screen behavior and extend UI
  and aggregate-status regression coverage.

## 0.42.0

- Start the administration information-architecture redesign with a stable
  two-row header, a horizontally scrollable navigation row and wider use of
  the available Home Assistant Ingress viewport.
- Move identity administration out of Overview into a dedicated top-level
  page and keep Overview consultative.
- Introduce the reusable responsive administration drawer with dialog
  semantics, focus trapping and restoration, Escape and overlay handling, and
  background-scroll prevention.
- Protect one-time credentials against accidental dismissal: closing the
  drawer requires explicit confirmation until the credential is acknowledged.
- Preserve French/English localization, dark theme and narrow-screen behavior,
  and add regression coverage for the new identity workflow.

## 0.41.0

- Replace the one-window grace implementation with one durable incident engine
  shared by simple mapping-level and bounded subject-aggregation modes.
- Require a stable non-empty subject in aggregated mode, retain every accepted
  alert and recovery, update repeated subjects without extending the original
  deadline, and treat unknown recoveries as audited no-ops.
- Promote all subjects still active at expiry into one deterministic versioned
  job input while preventing duplicate jobs under concurrent promotion.
- Bound subject count, subject size, aggregate input size and promotion retries;
  expose exhausted incidents and their blocking reason in the trigger view with
  an explicit administrator retry action.
- Replace the disposable development schema directly at generation 14 without
  migration code; this release requires App removal with data deletion and a
  clean reinstall.

## 0.40.7

- Restore `ghcr.io/home-assistant/base:latest` as the unpinned Docker base so
  every new build follows the current Home Assistant base image.
- Resolve and pull the current digest once at the start of each CI build, use
  that local image consistently, and retain its digest with the App version
  and source commit as a 90-day provenance artifact.
- Keep the resolved digest as OCI metadata on the CI-built image without
  turning traceability into a source-level version pin.

## 0.40.6

- Replace broad read/write/lock access to all of `/run` with the four exact
  s6 runtime subtrees and the single generated s6-rc link observed across 934
  HAOS audit records.
- Resolve `ghcr.io/home-assistant/base:latest` to the immutable OCI index
  digest `sha256:94ff231402a5e7ad2a82e261ad5fa4ffae7d7bb095c3febb2edbdf309c9b6aca`
  and build against that digest for reproducibility.
- Record the selected base name and digest in OCI image labels and print the
  resolved digest in the App startup log for operational traceability.

## 0.40.5

- Allow the single generated s6 shutdown stage executable at the exact path
  `/run/service/s6-linux-init-shutdownd/stage 4`.
- Account for AppArmor's hexadecimal audit encoding of paths containing a
  space, which excluded this final shutdown hook from the earlier transition
  inventory.

## 0.40.4

- Derive the enforced s6 execution allowlist from the complete HAOS
  complain-mode startup, operation, restart and shutdown audit instead of
  relying on process snapshots.
- Add every transient s6 IPC, supervision and oneshot executable observed in
  that audit, using exact installed package versions rather than recursive
  executable-directory rules.
- Grant read-and-inherit-execute only to generated s6 scripts, including the
  shutdown hooks and ephemeral oneshot runner; keep compiled executables on
  inherit-execute only.
- Add the exact shutdown executable chain (`s6-svlisten`,
  `s6-linux-init-shutdown` and the generated `halt` script) that was absent
  from the earlier partial audit analysis.

## 0.40.3

- Complete the exact s6 stop/restart allowlist with its three generated
  `.s6-svscan` termination scripts and the exact `s6-svc` alias and target.
- Allow directory enumeration of `/app` separately from recursive file reads.
- Disable Python bytecode generation at runtime instead of granting write
  access to source-tree `__pycache__` directories.

## 0.40.2

- Resolve the complete strict-mode startup denial batch captured from HAOS:
  exact `s6-overlay-stat`, `s6-ftrigrd` and s6 portable-utils multicall paths,
  the final shutdown template, and the single generated shutdown supervisor
  script under `/run/service`.
- Use exact installed package versions for the denied multicall targets after
  confirming that their broader version patterns did not authorize the loaded
  HAOS profile as intended.
- Keep recursive executable access to `/run`, `/command` and `/package`
  forbidden.

## 0.40.1

- Allow the exact `/command/s6-mkdir` startup alias and its s6 portable-utils
  multicall target, invoked by `preinit` before the process inventory can
  observe it.

## 0.40.0

- Complete the bounded HAOS AppArmor audit from 3,329 recorded accesses,
  reduced to nine unique operation, path and permission combinations.
- Allow the four missing transient s6 startup executables identified by the
  recorded profile transition chain and the `kill` capability used for child
  process lifecycle management.
- Remove AppArmor complain mode and restore full enforcement.
- Replace recursive writable access to all of `/data` with exact rules for the
  options file, SQLite database and its journal, WAL and shared-memory files,
  while retaining the already exact private credential rules.
- Add CI invariants preventing complain mode, broad executable-tree access and
  recursive persistent-data permissions from returning.

## 0.39.0

- Add a temporary AppArmor diagnostic release that replaces broad executable
  tree permissions with the exact application and s6 paths observed in CI.
- Run the profile in AppArmor complain mode for one bounded HAOS acceptance
  pass, allowing missing transient startup paths to be collected together
  instead of requiring iterative releases.
- Add a CI-only `strace` image and separate inventories for application
  executables, running s6 processes and available package executables; the
  distributed App image remains unchanged and contains no tracing utility.
- This diagnostic profile is intentionally temporary and must be replaced by
  the enforced final profile after the HAOS audit journal has been collected.

## 0.38.0

- Add aggregated overview metrics for ready connectors, ready tasks, events
  received over 24 hours and failed or dead-letter work over 24 hours.
- Add a French and English Ingress interface with browser-language detection,
  French fallback, localized dates and a persistent manual FR/EN selector.
- Translate static and dynamically inserted administration controls, primary
  states, confirmations, empty states and operational outcomes while leaving
  MCP names and upstream data unchanged.
- Add complete English and French App guides plus a bilingual Home Assistant
  `DOCS.md` quick-start document.
- Document Agent Control Plane in both language sections of the repository README and
  link both App guides from the repository support sections.
- Add repository invariants and unit coverage for language selection,
  documentation presence and the new bounded operational metrics.
- Keep sensitive and write-capable operations explicitly deferred to a later
  threat-review phase.

## 0.37.0

- Add reversible archival for tasks and MCP connectors while preserving every
  execution, report and audit entry linked to them.
- Refuse to archive a task with queued or leased work; archiving a task also
  pauses its schedules and event triggers and clears pending grace windows.
- Restore archived resources in a deliberately disabled state so an operator
  must explicitly reactivate them.
- Add administration filters for archived tasks and connectors, keeping normal
  operational views uncluttered.
- Improve human-readable rendering of free-form agent findings, including
  connector, virtual-tool, comparison and evidence fields.
- Include the read-only fake Streamable HTTP MCP server used to validate
  multi-connector routing and duplicate upstream tool names.

## 0.36.0

- Add an Ingress retention policy with a conservative 90-day default, bounded
  batches, an explicit preview and a confirmed manual cleanup action.
- Optionally run the same bounded cleanup automatically at most once every 24
  hours, persisting its policy and last-run time without a schema change.
- Delete only expired terminal executions and their reports and attempts, plus
  old events no longer referenced by a job or pending grace window.
- Never delete queued or leased work, configuration, identities, connector
  inventory, pending grace windows or audit entries.
- Add full cryptographic audit-chain verification and display its health and
  entry count alongside the retention controls.
- Audit every policy change and cleanup result while keeping the append-only
  chain intact.
- Close every SQLite connection deterministically after its transaction,
  preventing descriptor accumulation in the long-running App processes.

## 0.35.0

- Add interval, daily and weekly planifications with an explicit IANA timezone
  and deterministic next occurrences across restarts and daylight-saving time.
- Allow administrators to edit existing planifications and event triggers from
  their current forms instead of deleting and recreating them.
- Recompute the next occurrence after every planification change or resume,
  without replaying missed executions in a burst.
- Cancel an outstanding grace window and reset cooldown history when its event
  trigger is edited, keeping the changed route unambiguous and auditable.
- Fix conditional form sections so recovery and calendar fields are genuinely
  hidden when they do not apply.
- Preserve existing data through a direct schema-twelve upgrade, treating
  existing planifications as interval schedules.

## 0.34.0

- Add durable per-trigger grace windows from one minute to one hour, processed
  after App restarts by the bounded administration dispatcher.
- Add an administrator-defined recovery event type that cancels a pending grace
  window without creating a job; repeated alerts do not extend the deadline.
- Show pending deadlines and recovery routes in Ingress, and translate event
  outcomes into clear French operational labels.
- Cancel pending windows when their trigger, source identity or task is paused
  or revoked, and postpone promotion safely while dependencies, cooldown, an
  active task execution or the global queue prevent it.
- Preserve existing data through a direct schema-eleven upgrade with grace
  disabled for all existing triggers.

## 0.33.0

- Add a bounded event-input projection to each trigger: complete event, subject
  only, or attributes only.
- Keep the authenticated event complete in persistent history while giving the
  agent only the administrator-selected projection as its job input.
- Preserve existing triggers and data through a direct schema-ten upgrade,
  defaulting every existing mapping to the previous complete-event behavior.

## 0.32.0

- Add live execution-health counters for queued, leased and dead-letter jobs to
  the Ingress operations page.
- Add local filters for all, active and intervention-required executions so
  dead letters and their guarded relaunch action remain easy to find.
- Keep these operational views read-only and schema-free; existing data is
  preserved without a database upgrade.

## 0.31.0

- Add an explicit `Relancer` action for dead-letter executions in the Ingress
  operations view.
- Preserve the failed execution and all its attempts, while creating a fresh
  queued job from the same immutable task revision and input.
- Refuse relaunch when the task dependencies are unavailable, another execution
  of the task is active, or the bounded queue is full, and audit every decision.

## 0.30.0

- Add a configurable per-trigger cooldown from zero to seven days and expose
  its last successful trigger time in the Ingress interface.
- Persist every authenticated event during cooldown or while its task already
  has an active execution, but suppress duplicate jobs and record the exact
  reason in the event view and audit trail.
- Preserve generation-eight data through a direct schema-nine upgrade and
  retain existing triggers with cooldown disabled by default.

## 0.29.0

- Add administrator-managed event triggers binding one active event-source
  identity and exact event type to one ready task.
- Remove client-selected task routing from the public event contract; event
  sources can now enqueue only through an explicit active mapping.
- Suspend mappings when their source is revoked or their task becomes
  unavailable, with pause, resume and deletion controls in Ingress.
- Upgrade generation-seven databases in place while retaining existing
  identities, connectors, tasks, schedules, jobs and reports.

## 0.28.0

- Add persistent recurring schedules for ready task definitions with pause,
  resume and deletion controls in a dedicated Ingress page.
- Run the bounded scheduler only on the private administration process, skip
  missed occurrences after downtime and prevent duplicate active executions.
- Preserve existing generation-six databases through the first intentionally
  supported direct schema upgrade now that Phase 7 retains useful data.

## 0.27.0

- Restore the last administration page after a Home Assistant Ingress refresh
  instead of always returning to the overview.
- Present structured reports as human-readable summaries and findings while
  retaining the complete raw JSON in an optional disclosure.

## 0.26.0

- Advertise only the next queued job's virtual capabilities before its claim so
  MCP clients with a turn-scoped tool registry can use them after leasing.
- Continue to deny every advertised capability invocation until the same
  identity owns the matching active lease.
- Show the latest attempt outcome or failure reason directly in the execution
  queue instead of presenting retry failures as nonexistent reports.

## 0.25.0

- Notify MCP clients when task-scoped virtual tools appear after a claim or
  disappear after completion/failure, using Streamable HTTP notifications.
- Prevent duplicate manual executions for a task while one is queued or leased,
  both transactionally and in the administration interface.
- Let administrators immediately erase a newly issued identity secret from the
  page after copying it.

## 0.24.0

- Replace the identity status pill with the same compact green/red status dot
  used for connectors and tasks.
- Keep upstream connector identifiers and original tool names out of claimed
  job envelopes; workers receive only virtual capability names and schemas.

## 0.23.0

- Add an Ingress-only manual trigger for ready task definitions and switch
  directly to the execution queue after successful creation.
- Create manual jobs atomically against the current immutable task revision,
  rechecking connector/tool fingerprints and queue bounds server-side.
- Distinguish manual work from event-driven work without creating synthetic
  events, and record the administrator trigger in the audit trail.

## 0.22.0

- Dynamically expose each task-selected capability as an individual virtual MCP
  tool only while the authenticated identity owns that task's active lease.
- Preserve the original input schema while routing collision-resistant virtual
  names to exact connector/tool/fingerprint tuples without exposing endpoints,
  credentials or unselected tools.
- Invoke upstream Streamable HTTP MCP tools with bounded time and result size,
  redact normalized results and audit authorization, success and failure.

## 0.21.0

- Simplify task composition to agent instructions plus an exact selection of
  upstream tools; remove fixed-parameter configuration from the product flow.
- Preserve each selected tool's complete discovered input schema for its future
  virtual capability while keeping the collision-resistant gateway name.
- Keep upstream endpoints, credentials, original callable names and every
  unselected tool hidden from reasoning clients.

## 0.20.0

- Replace raw JSON constraint editing with schema-driven fixed-parameter fields
  using text, number, boolean and advertised-choice controls.
- Keep complex parameters agent-controlled until a safe dedicated editor exists
  instead of asking administrators to write protocol data manually.
- Enforce advertised enum and numeric bounds for fixed arguments server-side.

## 0.19.0

- Allow administrators to define bounded fixed arguments for each selected task
  tool and validate them against the discovered upstream input schema.
- Persist fixed arguments in immutable task revisions so future virtual tools
  can remove those values from agent-controlled input and inject them internally.
- Generate collision-resistant virtual capability names from stable task and
  connector identities, keeping identical upstream tool names unambiguous.

## 0.18.0

- Add pause and resume controls to configured tasks while preserving their
  connector and tool composition.
- Allow unused task definitions to be deleted and refuse deletion once a job
  references the task, preserving execution and report history.
- Record task lifecycle changes in the append-only audit journal.

## 0.17.0

- Replace the unbounded task tool checklist with a compact connector and tool
  selector that can add any number of tools from any ready MCP connector.
- Display only tool names in the task composer while retaining detailed tool
  documentation on the Connectors page.
- Derive the internal task identifier automatically from its visible name and
  remove that implementation detail from the administration interface.
- Use the same compact green/red task readiness indicator as connectors.

## 0.16.0

- Add the first generic task composer: name an objective and select exact tools
  from one or several ready MCP connectors.
- Snapshot every selected upstream tool schema fingerprint and compute task
  readiness from current connector, inventory and fingerprint dependencies.
- Prevent connector deletion while a task references it and include the exact
  namespaced tool selection in future job lease envelopes.
- Show the App version in the header, replace connector status badges with
  simple green/red/grey indicators, and make tool inventories collapsible.
- Separate reusable task definitions from their queued executions in the
  administration navigation.

## 0.15.0

- Add administrator-managed generic MCP Streamable HTTP connectors with no
  built-in server or vendor assumption.
- Test MCP initialization before creation, discover a bounded tool inventory,
  and support explicit recheck, enable, disable and deletion operations.
- Encrypt connector URLs and optional Bearer tokens at rest with a purpose-
  derived authenticated key; expose only a redacted origin to the interface.
- Keep discovered tools administrative and disabled for execution until the
  configurable task composer assigns exact tools in the next phase.

## 0.14.0

- Reset the prototype around a connector-neutral gateway: remove the fixed
  HA-MCP App option, health probe, inventory route and connector branding.
- Remove every built-in Gatus task, event/source literal and Home Assistant
  entity assumption; clean installations now start correctly with no task or
  connector.
- Accept bounded neutral event subjects and task names, resolve tasks only from
  persisted definitions, and validate completed reports against each task's
  stored report contract instead of one fixed diagnostic shape.
- Keep the Connectors page as an explicit zero-connector state ahead of the
  generic multi-MCP connector lifecycle implementation.

## 0.13.0

- Add an Ingress-only Connectors page with a bounded HA-MCP tool inventory for
  selecting the real read-only Gatus allowlist.
- Show only tool names, bounded descriptions and bounded input schemas; keep the
  inventory absent from the public HTTP and MCP surfaces.
- Return a bounded unavailable error when discovery fails without logging or
  returning the private HA-MCP URL.

## 0.12.0

- Add the protected private HA-MCP Streamable HTTP URL option using the same
  established `/private_<secret>` convention as Studio Code Server.
- Probe HA-MCP with an eight-second bound and show only configured, reachable
  and aggregate tool-count status in the Ingress dashboard.
- Keep the private URL and raw upstream tool inventory out of every public API,
  MCP response, audit record and log.

## 0.11.0

- Complete the phase-two queue foundation with an immutable versioned
  `gatus_readonly_diagnostic` task definition and schema references on jobs.
- Requeue transient failures and expired leases up to three attempts, then move
  the job to the visible dead-letter state while retaining every attempt.
- Limit each reasoning identity to one active lease and expose attempt counts in
  the administration task view.

## 0.10.0

- Add the first complete reasoning-client loop: atomic claim, bounded heartbeat,
  immutable report completion and explicit failure over MCP.
- Bind opaque lease tokens to both job and identity, store only keyed verifiers,
  and recheck current identity authorization on every operation.
- Expose a single worker permission in the UI while persisting the four explicit
  deny-by-default actions required by the protocol.

## 0.9.0

- Remove Alembic, SQLAlchemy and every development migration as requested for
  the pre-data development phase.
- Create the complete current SQLite schema directly on an empty App data
  directory and fail closed on an incompatible existing database.
- Establish the development rule that schema changes require an explicitly
  announced clean reinstall until the product reaches real-data testing.

## 0.8.0

- Add a persistent, transactional per-identity event intake limit, configurable
  from 1 to 600 new events per minute and defaulting to 30.
- Exempt idempotent replays from the quota and return audited HTTP 429 responses
  with a bounded `Retry-After` value when the limit is reached.
- Add the `0003_intake_rate_limits` migration so quota state survives listener
  restarts without affecting existing identities, events or jobs.

## 0.7.0

- Add CSRF-protected cancellation for queued jobs from the Ingress task view.
- Make cancellation an atomic `queued` to `cancelled` transition and reject
  missing or already terminal jobs without changing their state.
- Audit successful cancellations and every rejected cancellation request while
  keeping the mutation endpoint absent from the public listener.

## 0.6.0

- Add an Ingress-only audit view showing the 200 newest allowed and denied
  security decisions with actor, reason and redacted context.
- Add a chronological, versioned and redacted JSONL v1 audit export, bounded to
  10,000 records and carrying the existing integrity-chain hashes.
- Keep audit inspection entirely off the public listener and omit credential
  material from both representations.

## 0.5.0

- Complete the phase-one MCP read surface with exact event, job and report
  lookup tools alongside their existing bounded lists.
- Apply the same per-action discovery filtering and authorization checks to
  list and detail tools, with explicit not-found failures.
- Redact persisted event payloads, job inputs and report bodies again at the
  final detail boundary.

## 0.4.1

- Rebuild the MCP SDK settings model before initialization on Python 3.14,
  removing its harmless unresolved generic lifespan warning from App logs.
- Fail the container smoke test if that compatibility warning reappears.

## 0.4.0

- Add the authenticated stateless MCP Streamable HTTP endpoint at `/mcp`.
- Expose the first five versioned read-only tools for gateway status, effective
  permissions, events, jobs and reports.
- Filter tool discovery per identity policy and recheck authorization on every
  tool invocation using the existing opaque, independently revocable bearer.
- Avoid OAuth emulation and stateful MCP sessions; no connector secret or
  additional execution capability is introduced.

## 0.3.2

- Prevent an empty initial URL fragment from producing an invalid CSS selector
  and stopping all administration JavaScript before data loading begins.
- Validate navigation names against the four known views before changing tabs.

## 0.3.1

- Replace each administration loading state independently with either its data,
  a proper empty state or a visible bounded error state.
- Add authenticated public read APIs for events, jobs and reports, protected by
  their separate deny-by-default policy actions.
- Audit missing, invalid and insufficient credentials on all new read surfaces.

## 0.3.0

- Activate the Events, Jobs and Reports navigation pages in the Ingress UI.
- Add bounded, newest-first administration APIs for persistent events, queued
  jobs and structured reports.
- Show redacted event/report details, queue state and report counts without
  exposing credentials, verifiers or private connector state.
- Preserve direct tab selection through URL fragments and responsive navigation.

## 0.2.1

- Redesign the Ingress dashboard using the visual conventions established by
  UniFi Log Explorer, adapted to the Agent Control Plane navy, cyan and amber brand.
- Add the Agent Control Plane logo, compact navigation, clearer metrics, richer empty
  and identity states, and improved responsive behavior.
- Add a persistent local light/dark theme selector without external assets or
  weakening the self-only Content Security Policy.

## 0.2.0

- Add the first operational Ingress dashboard with service and identity totals.
- Add identity creation with composable control-plane permissions and one-time-only
  credential display.
- Add identity inventory and immediate revocation of all associated credentials.
- Serve the interface through a strict self-only Content Security Policy and
  preserve the Home Assistant Ingress prefix for every asset and request.

## 0.1.35

- Preserve the Home Assistant Ingress prefix in administration-page links.
- Validate the generated readiness link in the container smoke test.

## 0.1.34

- Remove all legacy private-state migration logic after the test installation
  data was explicitly deleted.
- Initialize and read private state exclusively as UID/GID 1000, pass the
  pepper in memory to both listeners, and remove the `fowner` capability.
- Validate a genuinely empty persistent volume through startup and restart.

## 0.1.33

- Apply the same owner/bootstrap-group traversal model to the `/data` parent
  (`1000:0:710`), completing restart access to the protected pepper chain
  without `DAC_OVERRIDE`.

## 0.1.32

- Permit only the runtime owner and root bootstrap group to traverse private
  state (`1000:0:710`) and read the pepper (`1000:0:640`).
- Keep runtime listeners on the in-memory pepper while allowing the confined
  launcher to bootstrap it again after a container restart without
  `DAC_OVERRIDE`.

## 0.1.31

- Bootstrap the persistent credential pepper once, before transferring the
  protected data tree, and pass it in memory to both runtime listeners.
- Prevent both concurrent Uvicorn processes from reopening the protected pepper
  file during application import while retaining persistence at mode `0600`.

## 0.1.30

- Add explicit AppArmor access for the persisted `credential-pepper` and its
  narrowly named atomic temporary files after HAOS showed that the generic data
  rule did not authorize reads of the protected secret.
- Include link permission required by atomic first-writer-wins pepper creation.

## 0.1.29

- Run CI ownership/mode assertions as the UID-1000 secret owner, preserving the
  intentional inability of root without `DAC_OVERRIDE` to traverse private data.

## 0.1.28

- Verify the secured private directory and pepper from inside the container so
  CI does not require host traversal of the intentionally protected `0700`
  directory introduced by 0.1.27.

## 0.1.27

- Migrate the exact persisted `credential-pepper` file from earlier attempts to
  UID/GID 1000 and mode `0600` before transferring its parent directories.
- Seed a root-owned, overly broad legacy pepper in CI and verify its ownership
  and permissions after startup.

## 0.1.26

- Invoke Alembic and Uvicorn as Python modules instead of `/usr/bin` console
  scripts, avoiding any need to grant AppArmor read access to those wrappers.
- Prevent future launcher changes from reintroducing Python console-script
  wrappers under `/usr/bin`.

## 0.1.25

- Migrate an existing `/data/private` before transferring ownership of its
  `0700` parent mount, preserving root traversal without `dac_override`.
- Retain idempotent runtime-user creation after the parent ownership transfer
  for fresh installations.

## 0.1.24

- Replace the AppArmor-sensitive `/data/private` existence test with an
  idempotent `mkdir -p`, followed by explicit ownership and mode enforcement.

## 0.1.23

- Split private-directory setup into a new-install path created directly as UID
  1000 and a legacy migration path using root `chown` plus `chmod 0700`.
- Restore only the narrow `fowner` capability required by HAOS for the legacy
  mode correction; continue to forbid `dac_override`.

## 0.1.22

- Migrate an existing root-owned `/data/private` directory from earlier app
  versions to UID/GID 1000 before enforcing mode `0700` as the runtime user.
- Seed that legacy ownership state in CI and verify the resulting owner and mode.

## 0.1.21

- Allow inherited execution of the exact `/sbin/su-exec` binary required to
  create private state and launch migrations/listeners as UID 1000.

## 0.1.20

- Create `/data/private` directly as the unprivileged runtime user after the
  `/data` ownership transfer, avoiding root access to a UID-1000-owned mount.
- Remove the now-unnecessary `fowner` capability instead of adding the broader
  `dac_override` capability.

## 0.1.19

- Transfer ownership of the `/data` mount without changing its Home
  Assistant-managed mode, allowing the unprivileged process to create SQLite
  state while retaining the exact `/data/private` initialization from 0.1.18.

## 0.1.18

- Stop changing the ownership and mode of the Home Assistant-managed `/data`
  mount itself; initialize only `/data/private`.
- Allow the exact `/data/` and `/data/private/` directory operations and the
  narrowly scoped `fowner` capability required to set private mode `0700`.

## 0.1.17

- Allow the narrowly scoped `chown` capability required to transfer the
  Home Assistant-mounted `/data` directories to the unprivileged runtime UID.

## 0.1.16

- Replace the `bashio` launcher dependency with a small POSIX shell launcher
  while retaining `with-contenv` environment import.
- Keep option loading, structured startup messages, signal handling, listener
  supervision, and unprivileged execution without widening AppArmor access.

## 0.1.15

- Allow read/execute access to the exact `/usr/bin/with-contenv` link and its
  canonical packaged s6-overlay target.

## 0.1.14

- Allow enumeration of the packaged s6-rc scripts directory and read/execute
  access to its five inventoried lifecycle scripts, using exact AppArmor rules.
- Lock the six-entry scripts inventory in CI.

## 0.1.13

- Allow read-only access to all 29 inventoried entries in the packaged s6-rc
  source tree, using exact file and directory rules rather than recursive access.
- Lock the expected packaged s6-rc inventory in CI so upstream changes fail
  validation instead of silently widening the AppArmor policy.

## 0.1.12

- Complete the exact seven-entry s6 service-definition allowlist by permitting
  enumeration of the empty `user2/contents.d` directory.

## 0.1.11

- Allow read-only access to the s6 `user2/type` service definition file.

## 0.1.10

- Allow `s6-rc-compile` to enumerate only the standard `user2` bundle directory.

## 0.1.9

- Allow `s6-rc-compile` to enumerate the `user/contents.d` bundle directory
  without granting read access to its entries.

## 0.1.8

- Allow read-only access to the s6 `user/type` service definition file.

## 0.1.7

- Allow reading the canonical s6-overlay target behind the
  `/command/printcontenv` symbolic link.
- Allow `s6-rc-compile` to enumerate only the `user` bundle directory, without
  granting read access to its contents.

## 0.1.6

- Allow the shell to read and execute only `/command/printcontenv`.
- Allow `s6-rc-compile` to enumerate `/etc/s6-overlay/s6-rc.d` without granting
  broad read access to the directory contents.

## 0.1.5

- Allow read-only access to the s6-overlay `rc.shutdown` template required to
  build the runtime shutdown script under `/run/s6`.

## 0.1.4

- Allow read-only access to the s6-overlay `rc.init` template required to build
  the runtime files under `/run/s6`.

## 0.1.3

- Allow the shell to read only the s6-overlay `stage0` script required after
  `preinit`, keeping file-by-file AppArmor permissions.

## 0.1.2

- Allow the shell to read the s6-overlay `preinit` script while retaining narrow
  AppArmor path restrictions.

## 0.1.1

- Allow the Home Assistant base image shell to read and execute `/init` under
  AppArmor.

## 0.1.0

- Add the initial non-root Agent Control Plane runtime.
- Separate the Home Assistant Ingress administration listener from the optional
  MCP and event listener.
- Add cold-backup SQLite persistence with an initial Alembic migration.
- Add liveness, readiness, French/English App translations, validation, and
  container smoke tests.
- Add the first persistent control-plane schema for identities, credentials,
  policy revisions, events, jobs, reports, and chained audit entries.
- Add deny-by-default policy primitives, HMAC-protected client credentials,
  recursive secret redaction, and atomic idempotent event/job creation.
- Add strict authenticated HTTP contracts for effective permissions and
  idempotent event intake.
- Restrict administration to the Supervisor Ingress source and context, protect
  credential creation with CSRF, and audit rejected public API requests.
