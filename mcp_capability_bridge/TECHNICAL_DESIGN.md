# MCP Capability Bridge — Technical Design

Status: **technical design fixed for implementation planning**.

This document translates `PROJECT_BRIEF.md` into implementation choices. It must not expand MCP Capability Bridge into a control plane, reasoning engine or workflow system.

## 1. Design goal

The Bridge remains one small authenticated MCP server around bounded technical adapters:

`MCP client -> Bridge core -> selected adapter -> configured target -> bounded result`

There is no suite-private protocol and no special runtime mode for Agent Control Plane or Agent Execution Plane.

The first release implements only:

- interactive **Web administration** through a real browser engine for HTTP/HTTPS interfaces;
- bounded **SSH** command capabilities.

Web and SSH are initial adapters, not hard-coded product limits.

## 2. Adapter boundary

The Bridge core owns only concerns that are common to every adapter:

- authenticated MCP endpoint;
- target registry and persistence;
- secret protection/redaction;
- adapter registration and dispatch;
- common input/result/resource bounds;
- concurrency accounting;
- administration shell;
- health and safe diagnostics.

Each adapter owns the technical semantics needed for its transport, including:

- adapter-specific target configuration validation;
- the MCP tools generated or configured for that target type;
- adapter-specific invocation/session behavior;
- target-envelope enforcement;
- adapter-specific connectivity tests;
- cleanup and technical error normalization.

The adapter interface must stay intentionally small. Adding another adapter later must not require changing MCP authentication, the existing Web/SSH implementations, ACP interoperability or Execution Plane interoperability.

No dynamic third-party plugin marketplace/loading system is required. Adapter registration may remain ordinary internal application code; modularity means **separation of responsibilities and independent adapter extension**, not a plugin framework.

## 3. Runtime baseline

Use the same proven HAOS-oriented foundation as Agent Control Plane where generic:

- `ghcr.io/home-assistant/base`;
- Python runtime;
- Starlette/Uvicorn for administration and health surfaces;
- official MCP Python SDK v2, pinned to an exact stable release when implemented;
- standard-library `sqlite3` for Bridge-owned persistence;
- `jsonschema` for bounded tool argument validation;
- `cryptography` for authenticated encryption of reversible target secrets;
- `asyncssh` for the initial SSH adapter;
- Alpine/system Chromium with a pinned browser-driving stack proven inside the HAOS base image for the initial Web adapter.

The preferred Web implementation is system Chromium plus Selenium/WebDriver using the HAOS/Alpine packaged browser/driver, avoiding browser downloads at runtime. If the exact HAOS base-image package combination requires an equivalent unprivileged driver, Codex may adapt that implementation without changing the MCP contract described below.

Dependencies are exact-pinned. Adapter-specific dependencies are installed only when required by adapters included in the App release. The App drops to an unprivileged `mcp-capability-bridge` runtime user after minimal `/data` preparation.

## 4. MCP compatibility

The Bridge uses standard MCP Streamable HTTP and the current stable official Python SDK v2.

The implementation must interoperate with both current MCP clients and the earlier MCP client generation used by the existing Agent Control Plane connector on the **same endpoint**, using ordinary SDK compatibility rather than a second deployment or private compatibility RPC.

Only tools are exposed. Prompts, resources, model sampling, jobs and task semantics are outside Bridge responsibility.

Tool inventory is deterministic and sorted by tool name. Configuration changes appear through ordinary MCP discovery behavior.

## 5. HAOS listeners

### Administration listener

- fixed container port `8099`;
- Home Assistant Ingress only;
- not published as a normal host port;
- serves administration UI and administration JSON endpoints;
- validates the Ingress boundary with the same defensive principles as ACP.

### MCP listener

- fixed container port `8098`;
- MCP endpoint at `/mcp`;
- `/health/live` and `/health/ready` on the same public listener;
- exposed through HAOS App `ports`, so the **host-side MCP port is user configurable** from Home Assistant Network settings;
- every MCP request requires the Bridge Bearer credential;
- browser-origin requests to the MCP endpoint are rejected unless a future explicit safe CORS use case is deliberately implemented.

Changing the host port never changes internal target configuration.

## 6. Health semantics

`/health/live` means the process is alive.

`/health/ready` means Bridge-owned persistence/configuration and listeners initialized successfully.

A configured target being offline does not make the App unready and must not create a HAOS watchdog restart loop. Target failures are operational states shown in Ingress.

## 7. MCP Bearer credential

The first release has one Bridge server-access credential.

Generation:

- cryptographically random opaque token;
- displayed only once on issue/replacement;
- never logged or returned later by administration APIs.

Storage:

- clear token never stored;
- verifier stored using an App-local random pepper/HMAC key under `/data/private`;
- constant-time verification.

Lifecycle:

- explicit issue;
- revoke;
- replace/rotate;
- old token invalid immediately after replacement.

There are no Bridge client identities/scopes. Possession of this token grants access to the Bridge's currently exposed tools. Fine-grained business authorization belongs elsewhere.

## 8. Reversible target secrets

Target credentials must be used by adapters, so they are reversibly protected.

Use an App-local authenticated-encryption key under `/data/private`. SQLite stores ciphertext plus safe metadata only.

Administration responses expose only safe presence/type indicators such as `has_secret`.

Stored Web usernames/passwords, HTTP Basic credentials, SSH passwords/private keys/passphrases and any future adapter secrets never appear in logs, tool schemas, page snapshots or MCP errors/results.

## 9. Persistence model

Use `/data/mcp_capability_bridge.db`.

Logical durable state:

### `settings`

- schema generation/version;
- bounded technical settings such as concurrency/session TTL defaults.

### `mcp_credential`

- verifier metadata only;
- replacement/revocation state and timestamps.

### `targets`

- immutable internal ID;
- stable administrator-visible key;
- display name;
- adapter type identifier (`web` and `ssh` initially, extensible later);
- enabled/disabled state;
- non-secret adapter configuration JSON;
- encrypted secret payload;
- timestamps.

### `ssh_capabilities`

- immutable internal ID;
- SSH target ID;
- globally unique stable MCP tool name;
- title/description;
- enabled/disabled state;
- strict input schema;
- fixed command/argument template;
- timeout/output bounds;
- timestamps.

Web action tools are deterministic adapter tools derived from each enabled valid Web target rather than administrator-authored browser workflows.

Future adapters may use only target configuration or may add their own adapter-owned persistence where genuinely necessary. They must not require redesigning the common target/authentication tables merely to add a transport.

No permanent invocation, browser-history, ACP-job or reasoning-history table is created.

## 10. Stable target-scoped tool identity

Each adapter owns the stable MCP identities it exposes while obeying global uniqueness.

Each enabled valid Web target with key `<target>` exposes a deterministic target-scoped Web tool family. Exact normalization is implementation-defined but stable after target creation.

Conceptual tools are:

- `<target>__web_open`
- `<target>__web_snapshot`
- `<target>__web_navigate`
- `<target>__web_click`
- `<target>__web_fill`
- `<target>__web_select`
- `<target>__web_press`
- `<target>__web_wait`
- `<target>__web_screenshot`
- `<target>__web_close`

The actual initial set may merge trivial actions if this reduces complexity without reducing the behavior in `PROJECT_BRIEF.md`.

Changing a target key after creation is compatibility-breaking and requires explicit confirmation because it may change adapter-generated MCP tool names. Changing a display title does not.

SSH capabilities retain their explicit stable administrator-defined MCP tool name.

## 11. Web target configuration

A Web target stores at least:

- fixed base URL with `http` or `https` scheme;
- explicit allowed top-level origin set, defaulting to the base origin only;
- TLS verification policy, default enabled;
- authentication mode and encrypted authentication material when required;
- session inactivity and absolute lifetime bounds;
- enabled/disabled state.

Initial authentication modes should cover the common local-administration cases without becoming a generic credential scripting system:

- no authentication;
- HTTP Basic authentication;
- configured form login using administrator-fixed login path/selectors and encrypted username/password values.

Form-login selectors are administrator configuration and are never supplied by the model. More complex SSO/MFA flows are outside the first release unless implementation evidence shows they can be added generically without weakening the boundary.

## 12. Web browser sessions

Interactive administration needs state across multiple MCP calls.

`web_open` creates an isolated browser context/profile and returns an opaque `session_id`. The session is bound to exactly one Web target.

Subsequent Web tools require that opaque session handle and may act only against the same target.

Sessions are:

- in memory only;
- bounded by inactivity timeout and absolute maximum lifetime;
- counted against a small browser-session concurrency limit;
- cleaned on explicit close, timeout, browser failure, App shutdown or restart;
- never automatically restored/replayed after restart.

A Bridge restart invalidates every browser `session_id`.

## 13. Web page representation

The primary model-facing page representation is **bounded text/structured data**, not raw HTML.

`web_snapshot` returns a compact page snapshot containing:

- safe current URL/path metadata;
- page title;
- bounded visible/accessibility text useful for reasoning;
- interactable elements with short opaque **element references** and useful labels/roles/state.

Element references are generated by the Bridge and are valid only for the current session/page generation. Navigation or material DOM change may invalidate them and require a fresh snapshot.

The model does **not** provide arbitrary CSS/XPath selectors. Actions such as click/fill/select operate on an element reference obtained from a Bridge snapshot.

This is both safer and easier for a model to use than exposing arbitrary selectors.

## 14. Web action semantics

### Open

Starts the target session, performs the configured login when required and lands on the configured administration origin.

### Navigate

Accepts only a relative path or another administrator-bounded same-target location. It cannot change scheme/host/port outside the allowed origin set.

### Click / fill / select / press

Operate only on current valid element references.

`fill` values may come from model arguments for ordinary form data, but stored Bridge authentication secrets are injected only by Bridge-owned login behavior and never returned to the model.

### Wait

Waits for bounded page/element/state change with a bounded timeout; it is not an unbounded sleep primitive.

### Screenshot

Provides a bounded screenshot for clients/models that can make use of image tool results. Basic Web operation must **not depend on vision**, because the text/accessibility snapshot is the normative representation.

### Close

Terminates browser/driver children and removes temporary profile data.

## 15. Web origin and browser security

The browser may render normal target pages, but the Bridge prevents model-driven escape:

- top-level navigation must remain inside allowed configured origins;
- every resulting top-level URL is revalidated after redirects/navigation;
- model arguments cannot supply arbitrary JavaScript;
- no DevTools/remote-debugging MCP surface;
- no arbitrary selectors;
- no file upload/download in the initial release;
- no arbitrary local filesystem path;
- no persistent unrestricted browser profile;
- browser profile/temp files are private and deleted after session cleanup.

The page itself is untrusted input to the reasoning model. The Bridge transports page state; it does not reinterpret page text as authorization or configuration.

## 16. Model-side requirement

Nothing in the Bridge requires a model-provider-specific Browser mode.

The consuming host must only expose the Bridge MCP tools through ordinary provider tool/function calling and return tool results to the model.

A non-vision model can operate the interface using `web_snapshot`. Vision support is optional for `web_screenshot`.

## 17. SSH target

An SSH target stores:

- hostname/IP;
- port;
- username;
- authentication type and encrypted credential;
- mandatory pinned/trusted host-key material;
- enabled/disabled state.

Host-key verification is always performed. Permanent “accept any host key” is not supported.

Initial credentials may include password or encrypted private key/passphrase where safely supported by `asyncssh`.

## 18. SSH capability

Each SSH capability defines one bounded command structure:

- fixed executable/command head;
- ordered argument template where each item is an administrator-fixed literal or one declared input property;
- strict input object schema;
- no caller-controlled whole command string;
- no PTY;
- no arbitrary environment map;
- no unrestricted stdin stream initially;
- per-capability timeout and output bound.

Values are converted/quoted safely; raw caller text is never concatenated as shell syntax.

The result contains bounded exit status/stdout/stderr and safe transport/timeout metadata. The Bridge reports technical result only; it does not infer business meaning.

## 19. Invocation concurrency and retries

There is no durable queue.

Use bounded in-memory concurrency:

- small global adapter operation limit;
- adapter-specific stricter limits where the runtime cost requires them, including browser sessions;
- immediate bounded `busy` failure when capacity is exhausted.

The Bridge performs **no automatic logical retry** of target operations. Ambiguous side effects are never replayed automatically.

## 20. Result and error bounds

Tool results use deterministic structured MCP output with compatibility text content where needed by the SDK.

Results never contain target secrets, auth headers, cookies, private keys or internal crypto material.

Adapter outputs have explicit hard size/resource limits. Oversized data fails boundedly rather than silently flooding the client.

Errors expose safe categories and useful technical messages, never stack traces or raw secret-bearing upstream exceptions.

## 21. Configuration lifecycle

Targets and adapter-specific capability definitions are managed through Ingress only.

Create/edit is persisted only after static validation by the target's adapter.

Connectivity tests are explicit and adapter-owned. For the first release:

- Web: browser startup + bounded target-origin reachability/login test;
- SSH: connect/authenticate + host-key verification without executing an arbitrary command.

SSH capability test explicitly executes the configured command and warns about possible side effects.

Target deletion/credential rotation or other execution-affecting changes are refused while that target is actively in use. Each active operation uses an immutable configuration snapshot.

## 22. Administration UI

Ingress follows ACP's visual language without copying ACP business concepts.

Header:

`MCP Capability Bridge vX.Y.Z`

with FR/EN and light/dark controls.

Primary common views:

- **Overview** — App/MCP state, credential state, target/tool counts, active sessions/invocations;
- **Targets** — generic target list plus adapter-specific create/edit/test/enable/disable/delete configuration;
- **MCP access** — issue/replace/revoke token and connection instructions.

Initial adapter-specific UI includes SSH capability configuration and Web target/browser state. Future adapters extend target/capability drawers or add a narrowly scoped adapter view only when needed; they do not create a second administration framework.

Stored secrets are never redisplayed.

## 23. Logs and observability

Logs are bounded/redacted.

Safe fields may include correlation ID, adapter type, safe target/tool key, duration, safe status category and byte counts.

Do not log by default:

- MCP arguments;
- browser page text/snapshots/screenshots;
- SSH stdout/stderr;
- credentials/cookies/private keys;
- stored secret values.

No permanent business audit/invocation history is required.

## 24. AppArmor and process boundary

AppArmor starts from the minimal observed runtime inventory rather than copying ACP verbatim.

Common baseline permissions cover only required Python/s6 runtime, application code, Bridge DB/private keys, temp/runtime paths and outbound stream sockets.

Each adapter may add only the AppArmor permissions required by its proven runtime. The initial Web adapter adds only the Chromium/WebDriver executables, libraries, shared-memory/temp/profile paths and child-process behavior demonstrated necessary by CI tracing and real HAOS testing. SSH uses only the network/runtime permissions actually required by its library implementation.

A future adapter must not inherit broad privileges simply because another adapter needs them. If an adapter cannot operate safely under a defensible HAOS/AppArmor boundary, that adapter is not accepted until its implementation is changed or the product-level security tradeoff is explicitly reconsidered.

## 25. Graceful shutdown

On SIGTERM/App stop:

- stop accepting new MCP work;
- boundedly drain simple active operations;
- invoke adapter-specific cleanup for remaining sessions/processes;
- terminate browser/driver children;
- close SSH/network resources;
- delete temporary browser profiles;
- never synthesize success for interrupted operations;
- never replay interrupted operations after restart.

## 26. CI design

CI grows by implementation lot and by adapter.

Common CI includes:

- metadata/source validation;
- exact dependency install;
- compile/unit tests;
- amd64 image build with base-image provenance;
- startup/health/Ingress smoke tests;
- secret non-disclosure;
- AppArmor executable inventory;
- restart/persistence tests;
- current and legacy-compatible MCP client tests against the same endpoint.

Every adapter adds deterministic adapter-specific fixtures without weakening or replacing the common tests.

Initial Web adapter fixture tests cover:

- page snapshot and stable element refs;
- click/fill/select/navigation;
- same-origin enforcement and redirect escape rejection;
- configured login without secret disclosure;
- session isolation/TTL/cleanup;
- text-only model path;
- optional screenshot path;
- App restart invalidating browser sessions cleanly.

Initial SSH fixture tests cover host-key verification, safe argument construction, injection probes, timeout/output bounds and no automatic retry.

ACP interoperability uses only standard MCP discovery/call behavior.

## 27. Production-data cutoff

Early development may replace schema generation only while explicitly operating on disposable test data.

Before the first production-ready release, the plan declares the persistence preservation cutoff. From that point, all supported Bridge target, credential and adapter-specific capability/configuration data require deterministic tested migrations on schema evolution.

## 28. Technical details not requiring product re-approval

Unless they alter visible behavior/security, the following are implementation decisions:

- Python module/class names;
- exact adapter registration/interface class names;
- exact SQLite DDL/indexes and per-adapter tables;
- exact stable MCP SDK v2 pin;
- exact Chromium/WebDriver package versions available in the HAOS base image;
- exact opaque session/element reference encoding;
- practical hard limits after test evidence;
- CSS/component reuse mechanics from ACP.

Any contradiction affecting independence, adapter extensibility, target power, MCP authentication, credential secrecy, target-envelope enforcement or visible HAOS behavior must be escalated before changing the product boundary.
