# Changelog

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
