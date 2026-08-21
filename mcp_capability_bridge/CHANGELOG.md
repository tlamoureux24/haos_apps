# Changelog

All notable changes to MCP Capability Bridge will be documented in this file.

## 0.4.1 — 2026-08-21

### Fixed

- Capture bounded, sanitized ChromeDriver/Chromium diagnostics under the stable `MCB_BROWSER_DIAG` DEBUG prefix when a HAOS browser session aborts.
- Convert Selenium session termination into the stable `browser_session_failed` API/UI error instead of an unhandled ASGI traceback.
- Preserve deterministic driver, process, diagnostic-file and disposable-profile cleanup on browser startup or navigation failure.

## 0.4.0 — 2026-08-21

### Added

- Added pinned Alpine Chromium 151.0.7922.108, matching ChromeDriver and Selenium 4.46.0 with executable inventory/AppArmor drift validation.
- Added the disposable browser runtime gate: UID 1000, bounded launch, fresh `/tmp` profiles, startup stale-profile cleanup, deterministic shutdown, disabled downloads/popups/background services and no writes under `/data`.
- Added static Web targets with explicit origin categories, administrator-confirmed DNS addresses, DNS-rebinding refusal, TLS policy and session lifetime limits.
- Added bilingual responsive Web target administration and an explicit disposable browser connectivity test while publishing zero Web MCP tools.

### Security

- Chromium uses the HAOS container/AppArmor boundary with no Linux capabilities and `no-new-privileges`; its unavailable container-internal sandbox is explicitly disabled rather than silently assumed.
- Browser resolution is pinned to confirmed addresses and all unlisted hostnames resolve to `~NOTFOUND`; unsupported schemes and origin-category escalation fail closed.

## 0.3.0 — 2026-08-21

### Added

- Added the bounded SSH adapter with password or private-key authentication encrypted at rest, fresh connections, no PTY/agent/forwarding/stdin/environment map, and deterministic cleanup.
- Added two-step host-key enrollment and explicit pinned-key rotation, SSH target/capability CRUD, and namespace publication through the existing generic MCP contract.
- Added absolute executable plus POSIX-token templates, scalar ACP-compatible schemas, per-call timeouts, separate bounded stdout/stderr drainage, secret redaction and explicit `effect_possible` failures.
- Added bilingual Ingress target, SSH capability and MCP access workflows using the established responsive right-drawer pattern.
- Added real SSH fixture tests for host-key refusal, password/private-key authentication, hostile token quoting, bounded output, timeouts, cleanup and fresh connections.
- Added a contract test proving that the current ACP discovers and invokes a real published SSH capability without Bridge-specific handling.

### Security

- Target and capability mutations are refused while the target is in use, and dispatch resolves the publication again under its lease to close administration races.
- Clear authentication secrets, arguments and remote output are neither persisted nor logged; known credentials echoed by a remote command are redacted from returned output.
- The SSH adapter exposes no caller-controlled command head or generic shell-command primitive.

### Acceptance

- Lot 2 was accepted on real HAOS: restricted SSH target/capability creation, direct and ACP/AEP invocation, fresh repeated connections, two-client namespace isolation, disable/re-enable, `In use` protection and restart persistence all passed without application error, credential disclosure or AppArmor denial.

## 0.2.0 — 2026-08-21

- Validate private-key Unix modes under the unprivileged service identity so the container smoke test preserves its deliberate `DAC_OVERRIDE` removal.
- Keep credential-persistence and ACP rotation contract tests deterministic for URL-safe secrets and rejected sessions.

### Added

- Added the authenticated MCP 1.28.1 Streamable HTTP endpoint with an intentionally empty production adapter registry.
- Added isolated MCP client namespaces with 256-bit one-time Bearer credentials, indexed HMAC-SHA-256 verification, constant-time comparison, rotation, revocation and revoke-before-archive lifecycle.
- Added separate atomic private keys for credential verification and authenticated target-secret encryption; clear credentials and target secrets are never stored.
- Added generic static adapter, target, capability and namespace-publication contracts with ACP-compatible tool-name and JSON Schema validation.
- Added namespace-scoped inventory revisions, `tools/list_changed` notification support, global/per-namespace operation limits, shared counters and emergency cancellation on credential rotation/revocation.
- Added functional MCP Clients, Targets and MCP Access views with one-time credential drawers and archived-client filtering.
- Added real contract tests against the current ACP MCP connector, including empty discovery, test-double publication/call, cross-namespace isolation and credential rotation.

### Security

- Public administration routes remain absent from port 8098, while `/mcp` rejects missing, unknown, rotated, revoked and archived credentials.
- AppArmor now permits only the two exact Bridge private-key files and their atomic temporary names in `/data/private`.

### Acceptance

- Lot 1 was accepted on real HAOS: two isolated MCP clients and ACP connected successfully, empty inventories remained isolated, credential rotation/revocation/archive behavior was immediate, configuration survived restart, and logs contained no secret, application error or AppArmor denial.

## 0.1.0 — 2026-08-21

### Added

- Added the installable HAOS App shell with synchronized metadata, authoritative assets and bilingual installation documentation.
- Added one unprivileged Python runtime owning isolated Ingress 8099 and public 8098 ASGI applications.
- Exposed only non-sensitive liveness/readiness routes on the public surface; MCP remains intentionally absent until Lot 1.
- Added generation-one metadata-only SQLite initialization and graceful shared-listener shutdown.
- Added the ACP/AEP visual foundation with FR/EN, light/dark themes, stable scrollbar geometry, responsive navigation, top-right action and accessible right drawer.
- Added a bounded AppArmor profile based on observed ACP/AEP S6 runtime executables and exact Bridge persistence paths.
- Added Lot 0 unit, repository, image, listener-isolation, restart and executable-inventory validation.

### Acceptance

- Lot 0 was accepted on real HAOS: both listeners ran under one PID, Ingress navigation and drawer behavior were correct, FR/EN and light/dark modes worked, mobile and desktop layouts remained stable, and stop/restart completed without error or AppArmor denial.
- Repository validation now requires the final HAOS-accepted Lot 0 status instead of its former pre-acceptance status.

### Design

- Reframed the Bridge as an independent, adapter-oriented MCP server that also integrates with ACP/AEP through their existing generic MCP boundary.
- Made isolated multi-client MCP namespaces, one-time credentials, publication boundaries and per-namespace Web sessions foundational requirements.
- Defined the initial statically packaged SSH and Web interactive adapters without enabling arbitrary runtime plugins.
- Clarified that Web authority is exactly the authority of the configured target account and must be presented as such to administrators.
- Added explicit SSH host-key enrollment, Web origin/network confinement, stale-reference protection, ambiguous-effect handling and secret/result sensitivity rules.
- Aligned the future HAOS Ingress administration UI with ACP/AEP conventions, including FR/EN, light/dark themes, right drawers, top-right actions and stable scrollbar behavior.
- Split browser delivery into packaging/confinement, read-only sessions and interactive-action lots, with real generic-client and ACP/AEP interoperability gates throughout.
- Added a dedicated threat model and replaced the previous implementation sequence with bounded acceptance-driven lots.
