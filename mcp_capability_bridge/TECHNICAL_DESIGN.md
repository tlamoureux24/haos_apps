# MCP Capability Bridge — Technical Design

Status: **technical design fixed for implementation planning**.

This document translates `PROJECT_BRIEF.md` into implementation choices. It must not expand MCP Capability Bridge into a control plane, reasoning engine or workflow system.

## 1. Design goal

The Bridge is one authenticated MCP server around bounded adapters:

`MCP client -> Bridge core -> adapter tools -> configured target -> bounded result`

The core owns MCP, authentication, target configuration, secret protection, generic adapter registration, bounds and HAOS administration. Adapter-specific mechanics remain behind adapters.

Initial adapters are **Web** and **SSH**. Future adapters must be addable without redesigning the MCP/authentication core or unrelated adapters.

## 2. Runtime baseline

Use the same proven HAOS-oriented foundation as Agent Control Plane where generic:

- `ghcr.io/home-assistant/base`;
- Python runtime;
- Starlette/Uvicorn for administration/health surfaces;
- official MCP Python SDK v2, exact-pinned at implementation time;
- standard-library `sqlite3`;
- `cryptography` for reversible target-secret protection;
- `jsonschema` for bounded tool arguments;
- `asyncssh` for SSH;
- one HAOS-compatible unprivileged browser-driving stack for the Web adapter.

The App drops to an unprivileged runtime user after minimal `/data` preparation.

## 3. Browser implementation choice

The architecture is **browser-engine neutral**.

The first candidate is system **Chromium + ChromeDriver + Selenium/WebDriver**, because the Alpine ecosystem used by Home Assistant provides Chromium and ChromeDriver together and ChromeDriver naturally creates a fresh temporary profile per driver session.

This candidate is not a permanent contract. Firefox/geckodriver or another suitable engine may replace it if real HAOS/AppArmor testing proves a simpler or safer implementation.

Playwright remains technically attractive for isolated browser contexts, but its official Linux support targets Debian/Ubuntu rather than Alpine. It therefore must not be selected merely for API convenience if that complicates HAOS packaging.

The accepted implementation is whichever engine/driver satisfies the same Web MCP contract while remaining unprivileged, bounded and reproducible on supported HAOS architectures.

## 4. MCP compatibility

Expose standard MCP **Streamable HTTP** on one endpoint. Use the current stable official Python SDK and preserve compatibility with the MCP generation used by the existing Agent Control Plane connector on that same endpoint.

Only MCP tools are exposed. Prompts, resources, model sampling, jobs and task semantics are outside Bridge responsibility.

No suite-private protocol or client-specific mode is introduced.

## 5. HAOS listeners

- Administration listener: fixed container port `8099`, Ingress-only, not normally published.
- MCP listener: fixed container port `8098`, `/mcp` plus non-sensitive `/health/live` and `/health/ready`.
- HAOS publishes `8098` through a user-configurable host-side Network mapping.

External target failures do not make the App unready and must not create watchdog restart loops.

## 6. MCP authentication

Use one Bridge-owned opaque Bearer credential initially.

The clear token is shown only once on issue/replacement. Store only a verifier protected with an App-local pepper/HMAC key under `/data/private`. Replacement immediately invalidates the old token.

There are no Bridge client identities or business scopes.

## 7. Target-secret storage

Target credentials must be usable by adapters, so store them using authenticated reversible encryption with an App-local key under `/data/private`.

SQLite contains ciphertext and safe metadata only. Administration APIs expose presence/type indicators, never stored clear secrets.

## 8. Persistence model

Use `/data/mcp_capability_bridge.db` for Bridge-owned configuration only.

Logical durable state:

- `settings` — schema generation and bounded technical settings;
- `mcp_credential` — verifier metadata;
- `targets` — stable ID/key, display name, adapter type, enabled state, non-secret configuration, encrypted secret payload;
- adapter-owned durable configuration tables only when an adapter genuinely needs them, such as bounded SSH capabilities.

The generic core must not hard-code Web/SSH-specific columns into its common target model.

No permanent invocation, browser-history, SSH-session, ACP-job or reasoning-history table exists.

## 9. Adapter registration model

Each adapter provides a small internal contract for:

- target configuration validation;
- optional target connectivity test;
- deterministic MCP tool definitions for enabled valid targets/configured capabilities;
- tool invocation dispatch;
- adapter-specific cleanup;
- safe status presentation metadata.

This is an internal extension point, not a public plugin ecosystem and not a workflow framework.

Adding a later FTP/SFTP/API adapter must not require changes to MCP authentication, unrelated adapters or suite integration semantics.

## 10. Ephemeral Web runtime

`web_open` creates a **new clean browser runtime session** for exactly one configured Web target.

The session may span multiple MCP calls because interactive administration requires continuity, but it is never durable.

Requirements:

- fresh temporary browser profile/context at open;
- never load cookies/cache/history/localStorage/sessionStorage/IndexedDB/profile state from a prior session;
- no saved storage-state file for reuse;
- no HAR/video/trace persistence in normal operation;
- downloads disabled in the initial adapter;
- session handle is opaque, memory-only and target-bound;
- inactivity and absolute session lifetime limits;
- close on explicit close, expiry, browser failure, App shutdown or restart;
- temporary profile/context deleted during cleanup;
- next `web_open` for the same target starts clean again.

If a driver creates a temporary on-disk profile internally, it must live only under Bridge-controlled temporary storage and be deleted deterministically when the session ends.

## 11. Web target configuration

A Web target stores:

- fixed `http`/`https` base origin;
- explicitly allowed top-level origins, default base origin only;
- TLS verification policy, default enabled;
- enabled state;
- bounded session timeouts;
- encrypted authentication material where required.

Initial authentication modes may include none, HTTP Basic and configured form login using administrator-fixed selectors/paths. Login secrets are injected by the Bridge and never returned through MCP.

## 12. Web MCP contract

Each enabled valid Web target exposes a stable target-scoped tool family equivalent to:

- `web_open`;
- `web_snapshot`;
- `web_navigate`;
- `web_click`;
- `web_fill`;
- `web_select`;
- `web_press`;
- `web_wait`;
- optional `web_screenshot`;
- `web_close`.

Exact names may be namespaced by target key.

`web_snapshot` returns bounded textual/accessibility state and Bridge-issued opaque element references. A model does not supply arbitrary CSS/XPath selectors.

Navigation may not escape configured allowed origins. Every resulting top-level URL is revalidated after navigation/redirect.

No arbitrary JavaScript, DevTools control, filesystem path, upload/download or persistent browser profile is exposed.

A non-vision tool-calling model must be able to complete the normal Web path using text/structured snapshots alone.

## 13. Web element references

Element references are generated by the Bridge for the current session/page generation. They are opaque and short-lived.

Navigation or material DOM changes invalidate stale references. An action on a stale reference fails safely and requires a new snapshot.

This prevents the model from turning the Browser adapter into arbitrary selector execution.

## 14. Ephemeral SSH runtime

Every SSH MCP tool invocation uses a **fresh SSH connection**.

Flow:

`validate call -> connect/authenticate/verify host key -> execute one bounded operation -> collect bounded result -> close channels/connection`

Do not persist or reuse:

- interactive shell/PTY;
- ControlMaster/multiplexing connection;
- SSH agent forwarding state;
- remote working-directory session;
- command history;
- stdout/stderr history;
- connection/session handles between MCP calls.

Only administrator configuration, encrypted credentials and trusted/pinned host-key material are durable.

## 15. SSH target and capability

An SSH target stores fixed host/IP, port, username, mandatory host-key trust, enabled state and encrypted credential.

Each SSH capability defines one bounded command structure:

- stable MCP tool name;
- strict input object schema;
- fixed executable/command head;
- ordered fixed/input argument template;
- no caller-controlled whole command string;
- no PTY;
- no arbitrary environment map;
- no unrestricted stdin initially;
- timeout/output bounds.

Caller values are safely converted/quoted and never concatenated as raw shell syntax.

## 16. Concurrency and retry

There is no durable queue.

Use bounded in-memory limits for adapter operations and a stricter browser-session limit. Capacity exhaustion fails immediately with a bounded busy error.

No automatic logical retry of Web actions or SSH commands. Ambiguous target side effects are never replayed automatically.

## 17. Result and logging policy

Tool results are bounded structured MCP content with compatibility text content as needed.

Never return target credentials, cookies, auth headers, private keys or internal crypto material.

Normal Bridge logs may retain only safe technical metadata such as correlation ID, adapter/target/tool key, duration, byte counts and status category.

Do not persist by default:

- MCP arguments;
- browser snapshots/page text/screenshots;
- browser cookies/storage/history;
- SSH command arguments;
- SSH stdout/stderr;
- target credentials.

## 18. Configuration lifecycle

Targets and adapter-owned capability definitions are managed through Ingress.

Create/edit is saved only after static validation. Connectivity tests are explicit and must avoid executing the target operation when a safer connectivity/authentication test exists.

Execution-affecting mutation or credential rotation is refused while the target is actively in use. Active operations use immutable in-memory configuration snapshots.

## 19. Administration UI

Ingress follows ACP's visual language without ACP business concepts.

Header: `MCP Capability Bridge vX.Y.Z` with FR/EN and light/dark controls.

Primary views:

- Overview;
- Targets;
- adapter-specific configuration sections/drawers;
- MCP access.

Stored secrets are never redisplayed. Web target state may show active ephemeral session count; no session history page is created.

## 20. AppArmor and process boundary

Start from minimal observed runtime inventory rather than copying ACP verbatim.

Baseline permits only required Python/s6 runtime, application code, Bridge DB/private keys, temporary paths and outbound stream sockets.

The Web lot adds only the selected browser/driver executables, libraries and temporary/shared-memory paths actually proven necessary.

The Browser adapter is not accepted if it requires privileged mode, broad host filesystem/device access or an unjustifiably broad AppArmor profile.

## 21. Graceful shutdown

On shutdown:

- stop accepting new MCP work;
- boundedly drain simple operations;
- terminate browser/driver children;
- close SSH/network resources;
- delete temporary browser profiles;
- do not synthesize success for interrupted work;
- do not replay work after restart.

## 22. CI design

CI grows by lot and includes metadata/source validation, exact dependency installation, container build/provenance, Ingress/health smoke tests, secret non-disclosure, AppArmor executable inventory and restart/persistence tests.

Web tests prove fresh-session isolation, no state leakage between two sessions to the same target, cleanup, origin confinement, textual snapshots, element-ref lifecycle and optional screenshot bounds.

SSH tests prove a fresh connection per invocation, host-key verification, argument injection resistance, timeout/output bounds, cleanup and absence of retained session/output state.

ACP interoperability uses standard MCP discovery/call behavior only.

## 23. Production-data cutoff

Before production readiness, schema replacement is allowed only on explicitly disposable test installations.

After the declared cutoff, target/credential/capability configuration is production data and schema evolution requires deterministic tested migrations.

## 24. Technical details not requiring product re-approval

Unless visible behavior/security changes, implementation may choose:

- exact Python class/module names;
- exact SQLite DDL/indexes;
- exact stable MCP SDK pin;
- Chromium vs Firefox or equivalent browser engine;
- Selenium/WebDriver vs another HAOS-proven unprivileged automation layer;
- exact temporary-profile implementation;
- exact hard limits after test evidence;
- UI component reuse mechanics from ACP.

Any contradiction affecting independence, adapter extensibility, target power, credential secrecy, ephemeral-runtime guarantees or visible HAOS behavior must be escalated before changing the product boundary.
