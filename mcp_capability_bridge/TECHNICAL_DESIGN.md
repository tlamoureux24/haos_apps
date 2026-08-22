# MCP Capability Bridge — Technical Design

Status: **authoritative technical design — Lot 4 production candidate implemented**.

This design implements `PROJECT_BRIEF.md` and must be read with `THREAT_MODEL.md` and the root architecture charter.

## 1. Architecture

The Bridge is one authoritative runtime around a generic core and statically packaged adapters:

```text
Ingress 8099 ─┐
              ├─ Bridge runtime ─ namespace/auth ─ registry ─ adapter ─ target
MCP 8098 ─────┘
```

Two distinct ASGI applications expose disjoint route sets and middleware while sharing one process-owned service container, locks, session registry and shutdown lifecycle. Uvicorn servers are started programmatically in the same event loop. Multiple worker processes are forbidden.

This choice prevents process-local divergence for target usage, browser sessions, namespace revocation, credential rotation and administration telemetry.

## 2. Runtime baseline

Reuse proven HAOS foundations from ACP where generic:

- `ghcr.io/home-assistant/base` with recorded provenance;
- Python and standard-library SQLite;
- Starlette/Uvicorn for administration and health;
- the exact MCP Python SDK generation compatible with current ACP, pinned at implementation time;
- `cryptography` for authenticated reversible target-secret encryption;
- `jsonschema` using the same admitted Draft 2020-12 subset as ACP;
- `asyncssh` for SSH;
- one HAOS-proven unprivileged browser/driver stack.

The App prepares `/data` minimally, then runs as a dedicated unprivileged UID. No adapter may require privileged mode, host networking or broad host filesystem access.

## 3. Network surfaces

Administration binds container port 8099 and is accepted only through the configured Home Assistant Ingress proxy address. CSRF protection, security headers and ingress-prefix-safe assets follow ACP conventions.

MCP binds container port 8098. It exposes authenticated `/mcp` plus non-sensitive `/health/live` and `/health/ready`. The HAOS host mapping is user-configurable.

An external target failure does not make the App globally unready. Readiness covers the Bridge runtime, database, private keys, registry and listeners.

CI proves that public paths never appear on the Ingress listener and administration paths never appear on the MCP listener.

## 4. Persistence and keys

Use `/data/mcp_capability_bridge.db` and `/data/private`.

Logical durable entities:

- schema/application metadata;
- MCP client namespaces;
- one active credential verifier per namespace plus safe rotation metadata;
- targets with stable IDs/keys, adapter type, enabled state and bounded non-secret configuration;
- encrypted target secret envelopes;
- namespace-to-capability publication mappings;
- adapter-owned configuration, initially SSH capabilities and Web target configuration;
- safe explicit connectivity-check state.
- the latest 500 payload-free operational Activity events.

Keys:

- a credential-verifier pepper, created atomically with mode `0600`;
- a separate authenticated-encryption key for target secrets, also atomic and `0600`;
- neither key is stored in SQLite or returned by any API.

No browser session, profile, page state, SSH connection, invocation argument,
snapshot, command output or business result is stored. The bounded Activity
journal persists only safe event/status/source/client/tool/adapter/duration
metadata and never a request or result payload.

## 5. Namespace authentication

Each namespace receives an opaque random 256-bit Bearer token formatted with a non-secret namespace/credential identifier and random secret component.

Store a fast HMAC-SHA-256 verifier under an App-local pepper. Authentication parses the bounded token, performs one indexed lookup, recomputes the verifier and uses `hmac.compare_digest`. Password KDFs are not used for opaque high-entropy tokens.

The clear credential is shown once. Rotation is transactional, invalidates the old verifier immediately, increments a credential generation and closes every Web session owned by the namespace. Revocation does the same and blocks discovery/calls. Archived namespaces remain revoked and are hidden by default in the UI.

Every authenticated request resolves exactly one namespace context. Tool discovery filters publications by that namespace. Session lookup requires namespace ID and credential generation in addition to the opaque handle.

Normal logs may include safe namespace ID/key and correlation ID, never the token or verifier.

## 6. Adapter registry

Adapters implement an internal protocol equivalent to:

- `type_key` and safe presentation metadata;
- validate target configuration and secret shape;
- perform an explicit non-operational connectivity/authentication check when possible;
- enumerate deterministic capabilities for one target;
- invoke one exact capability using an immutable configuration snapshot;
- clean target/runtime resources;
- expose safe status and resource counts.

The registry is assembled at build time. Unknown adapter types fail closed. There is no dynamic import path, uploaded package or executable plugin loader.

The core dispatch key is `(namespace_id, published_tool_name)`. It resolves to exactly one current target and adapter capability. Dispatch rechecks namespace, publication, target enabled/valid state and schema immediately before acquiring the operation lease.

## 7. Tool names and schemas

Each capability has a stable adapter-owned capability ID independent of its display name. Published MCP names are deterministic ASCII identifiers no longer than 64 characters so they remain compatible with current provider transports as well as ACP's 160-character discovery bound.

Suggested forms:

- SSH: `ssh_<capability_key>`;
- Web: `web_<target_key>_<operation>`.

Keys are normalized and collision-checked at creation. Renaming a display label does not rename a tool. Renaming a technical key is not supported after publication; replacement creates a new capability.

Schemas use the ACP-admitted Draft 2020-12 subset, are size bounded, have explicit object types, `additionalProperties: false`, explicit array `items`, bounded strings/arrays/numbers and no remote references. Discovery uses exactly the schema enforced at invocation.

MCP annotations are descriptive only. Adapter metadata may say read-oriented or effect-capable for operator understanding, but no authorization decision relies on those labels.

## 8. Publication and inventory changes

The administrator explicitly publishes capabilities to namespaces. Publication is many-to-many and contains no hidden argument rewriting or business policy.

Discovery returns only publications whose namespace, target and capability are active and valid. A known but unpublished/stale tool name returns a bounded `capability_not_available` error.

Changes affecting names, schemas, enabled state or publication update an inventory revision and emit `notifications/tools/list_changed` to connected sessions. ACP interoperability tests prove that changed schemas produce new fingerprints and make existing immutable task revisions fail closed.

## 9. Shared operation leases

The single runtime maintains:

- a global operation semaphore;
- per-adapter and per-namespace limits;
- per-target active-use counters;
- a per-Web-session lock;
- an immutable configuration snapshot per active operation.

Target edit, disable, archive, delete or secret rotation is refused while any target operation or Web session is active. Namespace rotation/revocation is allowed as an emergency security action: it cancels that namespace's sessions and operations, then invalidates the credential.

Administration reads the same authoritative counters. No state is inferred from another process's memory.

## 10. MCP call outcomes

Every result or error has a bounded machine category. Adapter calls track an effect state:

- `effect_possible: false` before an operation could have reached the target;
- `effect_possible: true` once an SSH exec request or effect-capable Web action may have been accepted.

Cancellation, timeout, transport loss and shutdown preserve this distinction. The Bridge never retries an adapter operation. A lost response may leave the caller uncertain and must never be reported as definite failure-without-effect.

An in-memory bounded request cache may suppress duplicate request IDs during one runtime, but it is not a durable exactly-once guarantee. Restart clears it. Clients must not retry effect-possible calls automatically.

## 11. SSH target onboarding

An SSH target stores host/IP, port, username, authentication mode, encrypted credential and a pinned server host key.

Initial authentication modes are password and encrypted private key with optional encrypted passphrase. SSH agents, agent forwarding and ambient host keys are forbidden.

Host-key enrollment is two-step:

1. perform a bounded unauthenticated key scan;
2. show host, resolved address, algorithm and SHA-256 fingerprint;
3. require explicit administrator confirmation;
4. persist the exact public key;
5. authenticate only after exact-key verification.

A changed key fails closed. Rotation repeats the explicit confirmation and is blocked while the target is active. The Bridge never silently trusts a first operational connection.

## 12. SSH capability model

Version one supports remote POSIX command execution without a PTY.

Each capability stores:

- stable key/display name and target ID;
- absolute executable token;
- ordered token template;
- strict input schema;
- timeout and separate stdout/stderr byte limits;
- enabled state.

Template entries are either administrator-fixed literals or references to one scalar input property. Arrays, nested objects, arbitrary environment variables and stdin are excluded initially.

All executable, fixed and input tokens are independently bounded and encoded with a reviewed POSIX single-token quoting function. NUL and disallowed control characters are rejected. No token is treated as a pipe, redirection, expansion or operator. The remote command string is the joining of quoted tokens only. The design explicitly acknowledges that SSH transmits a command string interpreted by the remote POSIX shell; it does not claim remote `execve(argv)` semantics.

Every invocation creates a new `asyncssh` connection, verifies the exact host key, disables forwarding/PTY, executes once, captures bounded UTF-8-compatible output, closes channels and connection in `finally`, and never retries.

Output is truncated with explicit metadata rather than unbounded buffering. Known Bridge secrets are removed. Arbitrary output remains potentially sensitive and is returned only to the authenticated calling namespace.

## 13. Browser implementation gate

The contract is engine-neutral, but selection is evidence-driven. The initial candidate is Alpine system Chromium plus matching ChromeDriver/Selenium. Playwright is not selected merely for convenience if it requires an unsupported Alpine stack.

Before Web MCP tools exist, CI and HAOS must prove:

- the exact browser/driver/helper executable inventory;
- Unix execute permissions and AppArmor `ix` coverage;
- unprivileged startup and termination;
- a fresh temporary profile under a dedicated non-persistent root;
- bounded `/dev/shm`, memory, process and child cleanup behavior;
- no profile writes under `/data`;
- startup cleanup of stale temporary directories after simulated crashes.

Internal browser instrumentation may use driver/network-control facilities, but no such facility is exposed to MCP clients.

## 14. Web target and network policy

A Web target stores:

- stable target key and display name;
- base `http` or `https` origin;
- administrator-confirmed resolved address set;
- navigation origins;
- authentication origins;
- auxiliary resource/WebSocket origins;
- TLS verification policy, enabled by default;
- encrypted authentication configuration;
- inactivity and absolute session limits;
- enabled state.

Default policy allows only the base origin. Additional origins are explicit and categorized; an auxiliary resource origin does not become a navigation origin. Credentials are injected only into the configured authentication origin/fields.

The browser request guard rejects unapproved schemes, hostnames, resolved addresses, redirects, frames, popups, WebSockets and downloads. `file:`, external `data:` navigation, `javascript:`, browser-internal URLs and filesystem access are prohibited. One session owns exactly one top-level browsing context.

Private/local addresses are not globally forbidden because they are the product's purpose, but every reachable private address must belong to the administrator-confirmed target envelope. Resolution changes fail closed until explicitly revalidated, preventing silent DNS rebinding into another local service.

TLS verification can be disabled only through an explicit warned administrator choice scoped to one target; this state is prominently visible.

## 15. Web authentication

Initial modes are none, HTTP Basic and bounded form login.

Form login configuration fixes the login path and administrator-supplied selectors used internally by the Bridge. The model never sees or supplies these selectors. Username, password and other configured secrets are encrypted and injected by the Bridge.

The login flow has bounded steps/time, verifies the resulting origin, never returns secret field values, and fails closed for MFA, CAPTCHA or unsupported redirect flows. SSO works only when all required authentication/navigation/resource origins are explicitly configured.

An explicit connection/login test starts a disposable session and performs no post-login operational click. Saving static configuration and testing connectivity remain distinct actions.

## 16. Web session manager

Session records are process-memory only and contain namespace ID, credential generation, target ID, timestamps, random handle digest, browser process/driver references, current page generation and one async lock.

Raw handles contain at least 256 random bits and are never logged or persisted. Lookup uses constant-time digest comparison where practical and always includes namespace/generation/target checks.

Open allocates a clean temporary directory, starts one browser context, performs configured login and returns only after a usable bounded snapshot state is available. Failure cleans everything and returns no handle.

Close is idempotent. Expiry, browser crash, target emergency invalidation, namespace rotation/revocation and shutdown all converge on the same cleanup routine. Startup removes only validated children of the dedicated temporary root.

## 17. Web snapshot and references

Snapshots are textual/structured and bounded by node count, depth, per-field length and total encoded bytes. They include only actionable/meaningful accessibility information required by a non-vision model.

Exclude password/hidden values, cookies, storage, headers, scripts, styles, raw HTML and known secrets. Ordinary visible page content can still be sensitive and is labeled accordingly.

Each snapshot increments a page generation and issues opaque references bound to `(session, generation, element fingerprint)`. Fingerprints include stable driver identity plus expected role/name/state. Before action the Bridge verifies generation, attachment, role/name/state and target context. Every attempted action invalidates the whole generation, whether it succeeds or fails.

Only one action or snapshot runs under the session lock. Asynchronous DOM/navigation changes that invalidate the expected element produce `stale_reference`, never selector fallback.

## 18. Web MCP operations

The initial family is:

- `open`: target-fixed, no URL or credential argument;
- `snapshot`: session handle only plus bounded optional pagination cursor;
- `navigate`: session handle plus bounded relative path/query within allowed navigation origins;
- `click`, `fill`, `select`, `press`: session handle, current reference and tightly typed value/key where relevant;
- `wait`: bounded condition enum and timeout, no arbitrary script;
- `close`: session handle.

No screenshot, upload, download, arbitrary selector, arbitrary URL, JavaScript, DevTools command or browser preference operation exists initially.

Actions report navigation/current safe origin metadata and `effect_possible`. Fill never permits writing into password fields unless that field is part of the Bridge-owned configured login flow, which is not model-driven.

## 19. Result transport and redaction

MCP results prefer bounded structured JSON and include compatible text content. All arrays have explicit item schemas, all objects have bounded known fields and results fit current ACP/AEP size limits.

Redaction combines:

- exact known-secret value replacement, including substrings;
- sensitive key-name removal;
- adapter-specific removal of cookies, headers and DOM sensitive fields;
- bounded safe error codes rather than upstream exception text.

Logs contain only correlation ID, namespace/target/capability IDs, adapter, duration, byte counts, effect possibility and safe outcome code. Arguments, snapshots, page text, stdout and stderr are not logged.

## 20. Administration UI

The Ingress UI reuses ACP/AEP conventions directly:

- authoritative icon and product/version header;
- horizontal menu and stable `scrollbar-gutter`;
- Overview plus MCP clients, Targets, SSH, Web and MCP access views;
- `pagehead split` primary actions at top right;
- the shared accessible right drawer pattern with overlay/close/`Esc`/focus restoration;
- one-time credential drawer with explicit “I copied the secret” acknowledgement;
- revoke then archive lifecycle and archived filters;
- clear target account-authority and TLS warnings;
- light/dark, FR/EN and responsive behavior;
- refresh on every view navigation and one non-stacking timer only on dynamic visible views.

The Overview distinguishes durable configuration from runtime activity. It may show active namespaces, published tools, enabled/invalid targets, active Web sessions, in-flight SSH calls and safe last errors. It does not show business jobs/reports.

## 21. Shutdown and crash recovery

On graceful shutdown the runtime stops accepting new calls, invalidates handles, cancels/drains within a hard deadline, closes SSH resources, terminates browser/driver process trees and deletes validated temporary profiles.

Interrupted operations never become success. Their final safe state preserves `effect_possible` when a target may have accepted an action.

After a crash or restart, no session is reconstructed. Startup validates and removes stale temporary profile directories before becoming ready. No target action is replayed.

## 22. CI and interoperability

CI grows per lot but current ACP compatibility starts in the authenticated-core lot, not final hardening.

It covers:

- exact metadata/dependency/version synchronization;
- two-listener route isolation in one runtime;
- namespace credential issue/rotation/revocation/isolation;
- cross-namespace session-handle rejection;
- target/publication inventory revisions and `tools/list_changed`;
- ACP discovery with current code and exact schemas/fingerprints;
- Bridge→ACP→AEP calls and bounded results/errors;
- no credential, target secret, argument or result leakage;
- real installed executable inventory versus AppArmor;
- browser and SSH cleanup under success, failure, timeout, cancellation and shutdown;
- restart persistence of configuration and bounded safe Activity metadata only;
- supported-architecture image construction and executable/AppArmor evidence.

HAOS acceptance remains mandatory for process, browser, networking, AppArmor and UI behavior.

## 23. Data cutoff

Version 0.7.0 is the final pre-cutoff candidate. Before the declared production
cutoff, schema replacement is allowed only for explicitly disposable test
installations. After its complete HAOS install, upgrade and backup/restore
acceptance, version 1.0.0 will declare generation 1 as the production cutoff.

After cutoff, every persisted namespace, verifier, target, encrypted secret, publication and capability configuration change requires a deterministic tested migration.
