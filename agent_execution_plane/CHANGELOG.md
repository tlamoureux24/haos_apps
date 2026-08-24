# Changelog

## 1.1.10

- Replace expected external-certificate tracebacks with one concise English
  listener-containment error containing the underlying cause.

## 1.1.9

- Hide HTTPS certificate guidance when the standalone API explicitly uses HTTP.

## 1.1.8

- Probe the configured Control Plane periodically even when no model or job
  polling is active, so certificate rotations immediately make stale trust
  visible as `certificate_sha256_mismatch` and recover after reconfiguration.

## 1.1.7

- Keep the configured ACP connection after a remote certificate rotation and
  report the runtime fingerprint mismatch precisely in status and logs.

## 1.1.6

- Reject a mismatched pinned ACP certificate with one safe diagnostic and a
  precise bilingual UI message, without leaking MCP SDK cleanup tracebacks.

## 1.1.5

- Keep CSRF protection functional when Home Assistant Ingress is opened over
  HTTP, while retaining Secure cookies for browser-facing HTTPS Ingress.

## 1.1.4

- Restrict the Home Assistant App to AMD64 only.

## 1.1.3

- Report a degraded service when the standalone HTTPS listener cannot start
  because its certificate is invalid.
- Show listener state on Transport & TLS and confirm neutral certificate
  regeneration with an explicit fingerprint-change warning.

## 1.1.2

- Enrich the Overview with real model availability, enablement, provider and
  in-use metrics.

## 1.1.1

- Move standalone server-certificate controls to a dedicated Transport & TLS
  page and clarify the separate outbound ACP trust setting.
- Correct translated Home Assistant network descriptions.

## 1.1.0

- Default the standalone API to HTTPS with a persistent self-generated or
  external certificate and keep Ingress administration independent.
- Add strict same-connection SHA-256 pinning for ACP and standalone MCP calls,
  certificate status/regeneration, HTTP warnings, and bilingual configuration.

## 1.0.2

- Correct the ACP worker setup guide: create an MCP client identity and grant
  only the four job lifecycle permissions that define the worker role.

## 1.0.1

- Expand the French and English guides with detailed model-family setup, ACP
  worker configuration, readable standalone JSON examples, lifecycle behavior,
  security boundaries, and troubleshooting.

## 1.0.0

- Promote the already stable Home Assistant App to the 1.0 production version
  after complete real-HAOS acceptance of standalone, OAuth, dynamic-tool, API
  and ACP-boundary operation.
- Preserve every execution, provider, MCP, standalone API, storage and ACP
  integration contract unchanged.

## 0.6.6

- Promote the Home Assistant App metadata from experimental to stable after the
  standalone, OAuth, dynamic-tool, API and ACP-boundary paths passed real HAOS
  acceptance.
- Preserve every execution, provider, MCP, standalone API and ACP integration
  contract unchanged.

## 0.6.5

- Add a minimal administration status endpoint backed by the real database
  readiness check.
- Drive the Overview service badge from that endpoint and show a bilingual red
  unavailable state on a failed or non-ready response.
- Preserve the existing `/health/live` and `/health/ready` contracts and all
  execution, standalone, provider and ACP-boundary behavior.

## 0.6.4

- Bound every ACP lifecycle exchange so a stalled MCP session cannot freeze job polling indefinitely.
- Supervise and automatically restart the ACP polling worker after an unexpected interruption while preserving normal shutdown cancellation.
- Expose safe bilingual timeout/restart diagnostics and verify recovery without restarting AEP.

## 0.6.3

- Present the configured singleton Control Plane connection as read-only state and move configure/replace actions into the shared administration drawer.
- Add durable generic ACP telemetry to Overview and the Control Plane page: connectivity, last successful claim poll, last ACP response, last-poll job availability, successful poll count, and last safe error.
- Keep telemetry source-neutral by deriving availability only from `jobs_claim_v1`, without querying ACP storage or introducing ACP-specific dependencies.

## 0.6.2

- Bound ACP connection validation to 15 seconds and emit safe `AEP_ACP_CONFIG` success/refusal diagnostics without logging the endpoint or credential.
- Give the Control Plane page an API-style top-right primary action with immediate progress, success, timeout, contract, and network feedback in French and English.

## 0.6.1

- Release the local slot after restart when the persisted ACP lease is already expired, while retaining no-replay reconciliation for leases that remain valid.
- Retry failure delivery safely with ACP's idempotent completion key and enforce the documented single consecutive transient heartbeat failure allowance.
- Validate lifecycle tool input signatures before saving an ACP connection and add contract tests against the current ACP implementation for schema validation, expiry recovery, heartbeat, idempotent failure, and no replay.

## 0.6.0

- Add the optional generic MCP Agent Control Plane boundary with validate-before-save encrypted worker configuration and ACP-independent readiness/standalone operation.
- Poll and claim only while the shared slot and a compatible model are available, map exactly `allowed_capabilities` into the common engine, and keep every ACP lifecycle tool outside model visibility.
- Add durable lease heartbeat/loss guarding, persist-before-delivery completion/failure retries, interruption reconciliation without replay, Ingress status/configuration, bilingual documentation, and contract regression coverage.

## 0.5.5

- Allow inheritance execution of every executable shipped by the pinned Codex 0.144.4 runtime: Codex, code-mode host, ripgrep, bubblewrap, and zsh.
- Validate the complete Codex executable inventory and Unix execute modes inside the amd64 image against the targeted AppArmor rules.

## 0.5.4

- Add bounded, sanitized DEBUG diagnostics for Codex subprocess lifecycle, JSON-RPC methods, unattended request refusals, and dynamic-tool dispatch without logging execution payloads or secrets.
- Drain Codex stderr concurrently and clean up its reader with the subprocess while preserving the existing unattended request policy and dispatch behavior.

## 0.5.3

- Align the Activity freshness indicator, credential workflow, and model forms with the ACP polling and right-drawer interaction patterns.
- Keep standalone API configuration in its dedicated metric while the overview detail reports only the execution lifecycle.

## 0.5.2

- Refresh the active Ingress view every five seconds while avoiding duplicate OAuth polling and preserving one-time credential disclosure semantics.
- Disable model edit, enable/disable, and delete actions while a model is in use, and surface `model_in_use` conflicts in the administration UI.
- Add an explicit one-time credential dismissal action and clear the displayed token when leaving the API view.

## 0.5.1

- Make model in-use state durable across execution and administration processes with SQLite-backed usage locking, while keeping priority reorder available.
- Return explicit `409 model_in_use` conflicts for unsafe model edits, disable operations, and deletes during execution.
- Preserve successful `null` execution results exactly across persistence and restart recovery.
- Replace the standalone credential verifier with a deterministic domain-separated SHA-256 verifier while continuing to store no recoverable credential.

## 0.5.0

- Add the authenticated asynchronous standalone execution API on port 8098 using the common Lot 2 engine and exact caller-supplied MCP operational envelope.
- Add one-time opaque credential creation/rotation, revocation, PBKDF2 verifier storage, and bilingual Ingress administration.
- Add the atomic durable active/pending single-slot lifecycle, repeatable GET, explicit ACK, stale-safe manual abandonment, and no-replay restart recovery.
- Preserve 0.4.2 models, priorities, activity and Codex state through an additive generation-1 schema extension.
- Add real Streamable HTTP MCP integration, concurrency, restart, bounds and non-persistence regression coverage.

## 0.4.2

- Clear the model form identity explicitly when opening creation after an edit, so multiple models sharing one ChatGPT OAuth account remain distinct.
- Add regression coverage for OAuth model creation, edit, persistence, and priority reorder.

## 0.4.1

- Add a reproducible real-Codex OAuth execution gate with a deterministic local capture provider.
- Enable Codex provider-native Web search through the canonical 0.144.4 top-level setting while keeping operational tools MCP-only.
- Serialize neutral tool results according to Ollama and OpenAI-compatible follow-up contracts.
- Add deterministic reversible collision-safe provider transport aliases for constrained function names.
- Keep Ingress views horizontally aligned by reserving a stable root scrollbar gutter.

## 0.4.0

- Add the source-neutral single-slot execution engine and exact source-supplied MCP operational capability envelope.
- Add pinned MCP Streamable HTTP and JSON Schema validation, complete-attempt deadlines, bounded tool dispatch, and conservative no-fallback-after-dispatch behavior.
- Extend Ollama-compatible, OpenAI-compatible, and ChatGPT OAuth providers with normalized tool loops and structured results.
- Characterize Codex-native reasoning helpers separately from AEP-supplied MCP operational tools and deny unattended runtime requests outside the bounded dynamic-tool path.

## Unreleased

- Clarify the normative ACP/AEP responsibility boundary: ACP remains the sole authority for connector governance and operational capability selection; AEP consumes the source-supplied model capability envelope, performs only technical consistency checks, and keeps ACP lifecycle tools outside model visibility.
- Clarify that MCP is the mandatory boundary for operational access to user infrastructure, while bounded provider-native reasoning/information helpers such as internal planning or public Web search may coexist when they cannot bypass MCP/ACP or access AEP private host state. Record the Codex 0.144.4 preflight observations as characterization inputs rather than a blanket zero-native-tools failure.

## 0.3.1

- Polish the bilingual Models table empty state, provider heading and provider-family labels.

## 0.3.0

- Add the official OpenAI ChatGPT OAuth provider family through the exactly pinned Codex 0.144.4 app-server over local stdio JSONL.
- Add shared device-code login, account/logout state and Codex model catalogue administration without exposing OAuth tokens or API-key fallback.
- Isolate Codex credentials under `/data/private/codex-home` and keep OAuth validation/health strictly non-inferential.

## 0.2.0

- Add encrypted configured-model persistence, deterministic ordering, enable/disable and positive per-model timeouts.
- Add Ollama-compatible metadata validation and OpenAI-compatible explicit tool-call validation.
- Add non-inference startup health and the bilingual responsive Models administration view.

## 0.1.2

- Align the Ingress administration container maximum width with Agent Control Plane at 1840 px.

## 0.1.1

- Align the generic s6-overlay AppArmor bootstrap rules with the HAOS-proven Agent Control Plane profile, including explicit directory traversal permissions.
- Clarify that the Docker executable inventory is evidence only and does not enforce or validate the HAOS AppArmor profile.

## 0.1.0

- Add the executable HAOS Lot 0 shell with isolated Ingress and standalone listeners.
- Add bilingual responsive light/dark administration views for Overview and Activity.
- Add generation-1 SQLite infrastructure and bounded persistent safe activity metadata.
- Add timestamped logging, unprivileged startup, AppArmor baseline, validation, tests, and CI.
