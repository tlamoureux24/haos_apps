# MCP Capability Bridge — Technical Design

Status: **technical design fixed for implementation planning**.

This document translates `PROJECT_BRIEF.md` into an implementation design. It must not expand MCP Capability Bridge into a control plane, agent runtime or generic workflow system.

## 1. Design goal

The implementation remains one small MCP server around bounded adapters:

`MCP client -> authenticated MCP endpoint -> capability registry -> adapter -> configured target -> bounded result`

Targets and capabilities are administrator configuration. The generic core knows MCP, configuration, schema validation, concurrency and result/error boundaries. HTTP, SSH and Browser mechanics stay inside their adapters.

There is no suite-private protocol and no special runtime mode for Agent Control Plane or Agent Execution Plane.

## 2. Runtime baseline

Use the same proven HAOS-oriented foundation as Agent Control Plane where it is generic:

- `ghcr.io/home-assistant/base` image;
- Python runtime;
- Starlette/Uvicorn for the administration and health HTTP surfaces;
- official MCP Python SDK **v2**, pinned to an exact stable release at implementation time;
- standard-library `sqlite3` for Bridge-owned persistence;
- `jsonschema` for capability input validation;
- `cryptography` for authenticated encryption of reversible target secrets;
- `httpx` for HTTP adapter calls;
- `asyncssh` for SSH adapter calls;
- Alpine/system Chromium plus a pinned Python browser-driving library for the Browser lot, selected and proven inside the HAOS base image before that lot is accepted.

Dependencies are exact-pinned in the implemented App. The runtime drops to an unprivileged `mcp-capability-bridge` user after startup preparation.

The Browser dependency is added only in the Browser lot so the earlier HTTP/SSH image and AppArmor baseline do not carry an unused browser attack surface.

## 3. MCP protocol compatibility

The primary MCP protocol target is the current **2026-07-28** revision over Streamable HTTP.

The official Python SDK v2 is deliberately chosen because one server endpoint can serve the 2026-07-28 stateless protocol and earlier 2025-era MCP clients. This lets a current client use modern MCP without breaking the existing Agent Control Plane connector simply because ACP may still speak the older revision.

No bridge-specific compatibility RPC is introduced.

The endpoint exposes tools only. Prompts, resources, model sampling, roots and task/job semantics are not Bridge responsibilities.

Tool inventory is deterministic and sorted by MCP tool name. Tool definitions use ordinary MCP fields:

- `name`;
- human-readable title/description;
- strict `inputSchema`;
- adapter-owned `outputSchema` where useful.

Tool annotations are optional descriptive hints only and are never interpreted as authorization.

Configuration changes that alter the visible tool inventory are reflected by subsequent standard `tools/list` discovery. Where the SDK/protocol revision supports list-change/cache behavior, it may be used normally, but correctness must not depend on a private notification path.

## 4. HAOS listeners

The App uses two listeners, following the proven ACP isolation pattern.

### Administration listener

- fixed container port `8099`;
- Home Assistant Ingress only;
- not published as a normal host port;
- serves the administration UI and administration JSON endpoints;
- validates the Ingress boundary using the same defensive principles as ACP.

### MCP listener

- fixed container port `8098`;
- Streamable HTTP MCP endpoint at `/mcp`;
- health endpoints at `/health/live` and `/health/ready`;
- exposed through HAOS App `ports` so the **host-side MCP port is user configurable** in Home Assistant Network settings;
- every MCP request requires the Bridge Bearer credential;
- any browser `Origin` header is rejected unless an explicit safe origin policy is later required, preventing the endpoint from becoming a browser-accessible DNS-rebinding surface.

Changing the host port does not change the internal listener or stored capability configuration.

## 5. Health semantics

`/health/live` reports process liveness only.

`/health/ready` reports that Bridge-owned configuration/persistence and listeners initialized successfully.

A target being offline, an SSH host being unreachable or an HTTP endpoint failing does **not** make the App unready and must not trigger a HAOS watchdog restart loop. Those are operational target/capability states surfaced through Ingress.

## 6. MCP Bearer credential

The Bridge has one server-access credential in the initial product.

Generation:

- cryptographically random opaque secret, with a recognizable Bridge prefix;
- displayed only once on issue/replacement;
- never returned later by administration APIs.

Storage:

- the clear token is never stored;
- a verifier is stored using an App-local random pepper/HMAC key under `/data/private`;
- comparison is constant-time.

Lifecycle:

- issue on first explicit administrator request or guided setup, not in logs;
- revoke;
- replace/rotate;
- old token becomes invalid immediately on replacement.

There are no per-client permissions, scopes or identity records. Possession of this endpoint credential authorizes access to the currently exposed Bridge tools. Fine-grained operational authorization is intentionally outside this App.

## 7. Reversible target secrets

Target credentials must be available to adapters, so they require reversible protection.

Use an App-local encryption key under `/data/private`, mode-restricted to the runtime, and authenticated encryption from `cryptography`.

SQLite stores ciphertext plus non-secret metadata, never raw SSH keys/passwords, HTTP bearer/basic credentials, fixed secret headers, Browser credentials or cookies.

Administration responses expose only presence/state indicators such as `has_secret` and safe credential type metadata.

Secrets are redacted from exceptions before logs/UI/MCP results.

## 8. Persistence model

A small SQLite database under `/data/mcp_capability_bridge.db` owns only Bridge configuration.

Logical tables:

### `settings`

- schema generation/version;
- bounded technical settings such as global invocation concurrency.

### `mcp_credential`

- verifier metadata only;
- created/replaced timestamp;
- revoked state if required by implementation.

### `targets`

- immutable internal ID;
- stable administrator-visible key;
- display name;
- adapter type (`http`, `ssh`, later `browser`);
- enabled/disabled state;
- non-secret adapter configuration JSON;
- encrypted secret payload;
- timestamps.

### `capabilities`

- immutable internal ID;
- target ID;
- globally unique stable MCP tool name;
- title/description;
- enabled/disabled state;
- strict input JSON Schema;
- adapter-specific operation JSON;
- timeout seconds;
- output byte limit;
- timestamps.

No invocation-history/job/reasoning table is created.

Transient active invocation state and current health/status remain in memory. Normal redacted App logs provide troubleshooting without becoming a durable business audit database.

## 9. Stable tool identity

Each capability has a globally unique MCP tool name separate from its editable display title.

The UI generates a safe default from target/capability keys, while allowing the administrator to choose the name at creation. After creation, changing the MCP tool name is treated as a compatibility-breaking operation and requires explicit confirmation; ordinary title/description edits do not change tool identity.

This prevents a cosmetic rename from silently invalidating clients such as ACP task revisions.

The Bridge adds no private fingerprint field. Clients may fingerprint the ordinary MCP name/schema/metadata themselves.

## 10. Configuration lifecycle

Targets and capabilities are managed only through the Ingress administration surface.

### Static validation

A create/edit is saved only if its configuration is structurally valid:

- target key/tool name uniqueness;
- URL/host/port syntax;
- capability JSON Schema validity and Bridge-supported bounds;
- adapter operation references only declared input properties;
- no forbidden caller-controlled target/credential field;
- positive timeout and acceptable output limit;
- Browser step validation once Browser support exists.

### Connectivity testing

Saving does not automatically execute a target operation merely to prove connectivity. A generic HTTP/SSH/Browser “test” can itself have side effects or consume credentials in target-specific ways.

The UI provides explicit test actions where a genuinely bounded technical check exists:

- HTTP target: DNS/TCP/TLS reachability without following redirects or sending a configured capability operation;
- SSH target: connect/authenticate and verify pinned host key without executing a remote command;
- Browser target: browser startup plus bounded origin reachability once Browser support exists.

A **capability test** is explicit and clearly states that it executes the actual configured operation and may have target side effects. Test results are not persisted as invocation history.

### Editing during use

Each invocation takes an immutable in-memory snapshot of its target/capability definition at dispatch. Destructive changes, credential rotation and deletion of a target/capability currently in use are refused with a clear `in use` state. Cosmetic metadata changes may be applied if they cannot affect the running invocation.

## 11. Capability schema rules

All MCP-visible inputs use JSON object schemas.

The Bridge validates arguments itself before adapter execution even if the MCP SDK has already validated them.

Security bounds include:

- root schema must be an object;
- no remote `$ref` resolution;
- bounded schema size/depth/property count;
- unexpected arguments rejected;
- string/array/object sizes bounded either explicitly by the schema or by Bridge hard safety limits;
- adapter mappings may reference only declared schema properties.

The administration UI may expose an advanced JSON Schema editor because this is more generic and smaller than inventing a second schema language. Validation errors are shown before save.

## 12. Invocation dispatch and concurrency

The MCP core resolves the requested tool name to one immutable capability snapshot, validates it, then calls exactly one adapter.

The App has a bounded in-memory global invocation semaphore. Initial default: **4 concurrent invocations**. The administrator may configure a small positive value within an implementation hard safety limit.

There is no durable queue. If capacity is exhausted, the call fails immediately with a bounded technical `busy` result/error that the client may choose to retry.

Browser invocations use their own stricter semaphore, initially one concurrent browser capability, because Chromium has a materially larger resource footprint.

A Bridge restart interrupts in-flight calls. They are not replayed automatically after restart.

## 13. Timeout and retry rule

Each capability has a configurable positive timeout; default **30 seconds** for newly created capabilities.

The timeout covers the complete adapter operation, including connection establishment and result collection.

The Bridge performs **no automatic logical retry** of tool invocations. This avoids duplicate side effects and keeps retry ownership with the caller.

An adapter may perform protocol-internal mechanics that do not repeat the target operation, but a second HTTP request, SSH command or Browser action sequence is not issued automatically after ambiguous failure.

## 14. Result bounds and error model

Adapter output is normalized to a deterministic object and returned as MCP structured content, with serialized text content as compatibility output where required by the MCP SDK/spec.

Results never include target credentials, secret headers, private keys, cookies or internal encryption material.

If a target response exceeds the capability output byte limit, the call fails with a bounded `result_too_large` technical error rather than returning silently truncated structured data.

Expected target/adapter failures are returned as tool execution errors visible to the MCP client. Protocol misuse such as unknown tool names remains an MCP protocol-level error as appropriate.

Errors include useful safe categories/codes but not stack traces or raw secret-bearing upstream exceptions.

## 15. HTTP target

An HTTP target stores:

- `http` or `https` base origin/base URL;
- TLS verification policy;
- optional basic/bearer authentication;
- optional fixed non-secret and encrypted secret headers;
- enabled/disabled state.

TLS verification defaults on. Disabling it is an explicit administrator choice shown clearly in the UI.

The target base origin is fixed administration state. MCP arguments can never provide or replace it.

## 16. HTTP capability

An HTTP capability defines:

- fixed method from a bounded method set (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`);
- fixed relative path template;
- explicit input-to-path placeholder mapping, URL encoded by the adapter;
- explicit input-to-query mapping;
- optional fixed JSON body plus explicit input-property-to-JSON-location mappings;
- optional fixed capability headers that cannot override protected auth/host headers;
- timeout/output limit inherited from the common capability model.

No caller-controlled arbitrary URL or header map is accepted.

Redirects are disabled. A redirect response is returned/fails as a target result rather than followed to a different origin.

For JSON responses, the adapter returns parsed JSON when valid and within bounds. Otherwise it returns bounded text with content type/status. Response authentication headers such as `Set-Cookie` are not returned to the MCP client.

A stable HTTP result object contains at least:

- status code;
- content type when known;
- parsed JSON body or text body;
- success/error indication derived only from transport/HTTP mechanics, not business semantics.

## 17. HTTP SSRF boundary

The model/caller cannot choose a host, scheme or port. The administrator-created target determines the origin.

Redirect following is disabled. URL templates accept only relative paths and adapter-encoded path/query values; they cannot switch scheme/authority.

Private/local network targets are intentionally supported because this App is designed for local infrastructure. Therefore blanket RFC1918 blocking is not appropriate. SSRF protection is achieved by **administrator-fixed origin + no caller origin override + no redirect escape**, not by forbidding local addresses.

## 18. SSH target

An SSH target stores:

- hostname/IP;
- port;
- username;
- authentication type and encrypted credential;
- mandatory pinned host key or trusted known-host key material;
- enabled/disabled state.

Host-key verification is always performed. “Accept any host key” is not a supported steady-state mode.

Authentication initially supports encrypted private-key and password credentials where `asyncssh` supports them safely. Private key passphrases are encrypted Bridge secrets.

## 19. SSH capability

An SSH capability defines one command structure:

- fixed executable/command head;
- ordered argument template where each element is either an administrator-fixed literal or one declared input property;
- no caller-controlled whole command string;
- no PTY;
- no arbitrary environment map;
- no unrestricted stdin stream in the initial implementation.

The adapter converts values according to the declared schema and builds the remote command using POSIX-safe argument quoting; it never concatenates raw caller strings into shell syntax.

Administrators remain responsible for the privilege of the configured remote account. A restricted account/forced-command/sudoers boundary is recommended for sensitive targets.

The SSH result object contains:

- exit status;
- bounded stdout;
- bounded stderr;
- transport/timeout category where applicable.

The Bridge does not decide whether a non-zero exit code is a business failure beyond reporting the technical exit status.

## 20. Browser target

Browser support is isolated in its own implementation lot.

A Browser target stores:

- one fixed base origin and optional explicit same-target allowed origins;
- encrypted named secret values used only by configured steps;
- TLS policy;
- enabled/disabled state.

The browser runtime uses HAOS-packaged/system Chromium. It must not rely on privileged host browser access.

Each invocation uses an isolated temporary browser profile/context under a Bridge-controlled temporary directory and cleans it up after success, failure, timeout or cancellation.

## 21. Browser capability

A Browser capability is a small fixed administrator-defined sequence of bounded steps, not a general workflow engine.

Initial allowed step types are deliberately limited to:

- navigate to a fixed relative path on an allowed origin;
- wait for a fixed selector;
- fill a fixed selector from a literal, declared MCP argument or named Bridge target secret;
- click a fixed selector;
- select a fixed option from a literal or declared MCP argument;
- extract text from a fixed selector into a named result field;
- extract a fixed attribute from a fixed selector into a named result field.

Explicitly not supported initially:

- arbitrary JavaScript evaluation;
- arbitrary caller-selected URL/origin;
- arbitrary DOM selector supplied by the caller;
- file upload/download;
- arbitrary filesystem access;
- persistent unrestricted browser profiles;
- generic DevTools/browser remote-control exposure.

Browser output is the bounded extracted result map plus safe final-page metadata needed for diagnosis. Raw whole-page HTML is not returned by default.

## 22. Administration UI

Ingress follows ACP's established graphical language without copying ACP business concepts.

Header:

`MCP Capability Bridge vX.Y.Z`

with FR/EN and light/dark controls.

Primary views:

- **Overview**: App/MCP state, endpoint/credential state, configured/available target and capability counts, current invocation count;
- **Targets**: create/edit/disable/delete targets and rotate target credentials;
- **Capabilities**: create/edit/disable/delete capabilities, inspect generated MCP schema and run explicit test;
- **MCP access**: issue/replace/revoke the one-time Bearer credential and show connection instructions;
- adapter-specific configuration drawers within Targets/Capabilities rather than separate product-specific pages.

The UI never displays stored secrets after creation/rotation.

## 23. Logs and observability

Application logs are bounded and redacted.

Safe log fields may include:

- correlation/request ID;
- adapter type;
- target/capability internal ID or safe key;
- duration;
- safe technical status category;
- byte counts.

Logs must not include:

- MCP arguments by default;
- full target response bodies;
- SSH stdout/stderr by default;
- Browser page content;
- authorization headers/credentials;
- private keys/passwords/cookies;
- fixed secret values.

The UI may show the last safe technical state/error for a target/capability in memory, but no permanent invocation audit history is required.

## 24. AppArmor and process boundary

The AppArmor profile starts from the actual minimal runtime inventory rather than copying ACP verbatim.

Common permissions include only:

- Python/runtime/s6 startup executables required by the Home Assistant base image;
- read-only application code;
- read/write Bridge database and `/data/private` key material;
- `/tmp` runtime files;
- outbound IPv4/IPv6 stream sockets;
- no host filesystem/device access beyond what the actual adapter needs.

HTTP/SSH baseline must be accepted with this small profile first.

The Browser lot extends AppArmor only for the installed Chromium executable, its required libraries, shared-memory/temp/profile files and child-process behavior proven by trace + HAOS testing. Browser support must not grant a shell or broad host filesystem access.

## 25. Graceful shutdown

On SIGTERM/App shutdown:

- stop accepting new MCP calls;
- allow a short bounded drain window for active HTTP/SSH invocations;
- cancel remaining adapter tasks after the drain window;
- close SSH/network resources;
- Browser lot terminates Chromium/driver child processes and deletes temporary profiles;
- commit no synthetic success for interrupted calls;
- shut down listeners cleanly.

No interrupted target operation is automatically replayed on restart.

## 26. CI design

CI is dedicated to MCP Capability Bridge and grows by lot.

Always include:

- metadata/source validation;
- exact dependency install;
- compile/unit tests;
- amd64 container build with base-image provenance recording;
- startup/health/Ingress smoke tests;
- secret non-disclosure checks;
- AppArmor executable inventory and expected-runtime checks;
- restart/persistence smoke tests.

MCP core tests include both:

- modern 2026-07-28 client behavior;
- legacy/2025-compatible client behavior on the same endpoint.

Adapter tests use local deterministic fixtures:

- local HTTP test server with redirect, oversized-response and auth cases;
- local AsyncSSH server with pinned host key, argument-injection probes and timeout/output cases;
- Browser lot local web fixture with same-origin/forbidden-origin, selector, secret-fill, timeout and cleanup cases.

ACP interoperability is tested using standard MCP discovery/call behavior only.

## 27. Production-data cutoff

During early development before the first accepted production release, schema generation may still be replaced on clean test installations if explicitly planned.

The implementation plan must declare a production-data preservation cutoff before the Bridge is treated as production-ready. From that cutoff onward, targets, capabilities and credentials are non-disposable and every schema evolution requires explicit deterministic tested migration.

## 28. Technical decisions that do not require product re-approval

The following remain implementation details unless they change visible behavior/security:

- exact Python class/module names;
- exact SQLite DDL/indexes;
- exact current stable MCP SDK v2 pin selected when Codex implements the lot;
- exact Starlette route/module split;
- exact crypto envelope encoding;
- exact safe hard limits after tests determine practical values;
- exact Alpine Chromium/browser-driver package chosen in the Browser lot;
- CSS/component reuse mechanics from ACP.

A contradiction affecting independence, exposed capability power, credential/auth semantics, adapter scope or visible HAOS behavior must be escalated before implementation changes the product boundary.