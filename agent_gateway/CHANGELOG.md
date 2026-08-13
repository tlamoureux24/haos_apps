# Changelog

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
  UniFi Log Explorer, adapted to the Agent Gateway navy, cyan and amber brand.
- Add the Agent Gateway logo, compact navigation, clearer metrics, richer empty
  and identity states, and improved responsive behavior.
- Add a persistent local light/dark theme selector without external assets or
  weakening the self-only Content Security Policy.

## 0.2.0

- Add the first operational Ingress dashboard with service and identity totals.
- Add identity creation with composable gateway permissions and one-time-only
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

- Add the initial non-root Agent Gateway runtime.
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
