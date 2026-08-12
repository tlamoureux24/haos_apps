# Changelog

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
