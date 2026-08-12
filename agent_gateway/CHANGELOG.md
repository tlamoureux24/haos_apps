# Changelog

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
