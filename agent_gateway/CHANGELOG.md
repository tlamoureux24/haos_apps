# Changelog

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
