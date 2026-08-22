# Changelog

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
