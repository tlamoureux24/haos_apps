# MCP Capability Bridge — Project Brief

Status: **functional scope fixed — technical design and implementation plan follow this brief**.

This document defines the product boundary and visible requirements of MCP Capability Bridge. The root `ARCHITECTURE_CHARTER.md` remains normative; where this brief is more specific, the narrower MCP Capability Bridge responsibility applies.

## 1. Product purpose

MCP Capability Bridge is a **generic MCP server that exposes bounded access to non-MCP technical systems**.

Its responsibility is deliberately small:

1. let the administrator configure a technical target;
2. expose a bounded MCP tool surface appropriate to that target type;
3. validate every invocation against the administrator-controlled target envelope;
4. execute the corresponding technical operation;
5. return a bounded, sanitized MCP result.

Conceptually:

`configured technical target -> bounded adapter tools -> MCP -> any compatible MCP client`

The Bridge is not a reasoning engine, control plane, task system, scheduler, workflow engine or agent runtime.

## 2. Independence and genericity

MCP Capability Bridge must remain fully useful by itself.

It does **not** require Agent Control Plane or Agent Execution Plane. Any compatible authenticated MCP client can use it directly.

When Agent Control Plane is used, the Bridge appears exactly as an ordinary upstream MCP server. No private API, shared database, special task contract or suite-only back channel is introduced.

When Agent Execution Plane uses a Bridge directly, it does so through the same standard MCP surface as any other client.

The core must not contain product-specific behavior for Home Assistant, OpenDTU, Cerbo GX, UniFi, Gatus or any other appliance. Those systems are only possible configured targets.

## 3. Modular adapter model and initial scope

MCP Capability Bridge is **adapter-oriented and extensible**.

The generic MCP/authentication/configuration core must allow later target types to be added as separate bounded adapters without redesigning unrelated adapters or coupling the Bridge to a particular client.

The first implementation focuses only on:

- **Web administration interfaces**, reached through HTTP or HTTPS and operated through a real browser engine;
- **SSH targets**, reached through deliberately bounded configured commands.

These are the **initial adapters**, not the architectural limit of the Bridge.

Future needs may justify additional adapters such as FTP/SFTP, a direct bounded API adapter or another technical transport. Those are intentionally outside the current implementation plan and must each be designed as a bounded extension.

## 4. Core separation rule

The key responsibility split is:

> **MCP Capability Bridge defines the maximum technical capability; Agent Control Plane, when present, defines operational authorization.**

The Bridge owns target connection configuration, target credentials it directly needs, adapter-specific MCP tools, strict argument/target-envelope validation, bounded runtime resources, adapter cleanup, result sanitization and the MCP server endpoint.

The Bridge does not own models, agents, tasks, jobs, leases, reports, schedules, triggers, events, Control Plane identities or business-scenario authorization.

## 5. Ephemeral runtime rule

**Target runtime state is disposable by default.**

The Bridge persists administrator configuration because it must survive restarts, but it does not persist technical session state produced while using a target.

### Web

Each `web_open` equivalent starts a **fresh isolated browser session**, comparable to a new private/incognito window.

Multiple MCP actions may use that same short-lived session because interactive browsing requires continuity between page inspection, clicks, form filling and navigation. However:

- the session starts from a clean state;
- no previous session cookies, browser history, cache, local storage, session storage, IndexedDB or browsing profile are loaded;
- no browser storage state is deliberately exported for reuse;
- no HAR, video, trace or download archive is persisted as normal operation;
- stored Bridge credentials may be injected only to establish the configured target login and are never exposed to the MCP client/model;
- closing, expiry, App shutdown, browser failure or App restart destroys the session and its temporary data;
- the next Web session starts clean again.

This rule applies even when reconnecting to the same configured Web target.

### SSH

Every SSH tool invocation opens a **fresh SSH connection**, executes exactly the configured bounded operation and closes the connection afterwards.

The Bridge does not keep a persistent shell, PTY, connection pool/multiplexed control session, agent-forwarding state, remote working session or command/output history between calls.

Target configuration and encrypted credentials remain durable because they are administrator configuration; SSH runtime state does not.

### Diagnostics

The Bridge may retain only minimal redacted application logs needed for technical diagnosis, such as safe target/tool identifiers, status category and duration. It must not persist Web page contents, browser snapshots, cookies, SSH command arguments, SSH stdout/stderr or target secrets as an invocation history.

## 6. Web administration target

A Web target represents an administrator-configured **HTTP/HTTPS administration interface**.

The objective is to let a reasoning model interactively inspect and operate that configured interface through ordinary MCP tool calls. The model does not need a native browser feature; it only needs ordinary tool/function calling from its host.

A Web target owns at least:

- fixed base origin and explicitly allowed same-target origins;
- TLS policy;
- authentication material required by the Bridge;
- bounded browser-session limits;
- enabled/disabled state.

For an enabled valid target, the Bridge exposes deterministic target-scoped tools equivalent to:

- open a fresh session;
- inspect the current page as bounded text/structured accessibility state with Bridge-issued element references;
- navigate only inside the configured origin envelope;
- click a referenced element;
- fill/select/press using referenced elements;
- wait for bounded page/state changes;
- optionally obtain a bounded screenshot;
- close the session.

The model cannot supply arbitrary external URLs, arbitrary JavaScript, unrestricted selectors, DevTools commands, filesystem paths, downloads/uploads or browser credentials.

The primary page representation is textual/structured so a non-vision model can operate the interface. Screenshot support is supplementary.

## 7. Browser-engine neutrality

The product contract does **not** require Chromium specifically.

The implementation must use whichever unprivileged browser + automation stack is simplest and safest to package under HAOS/AppArmor while satisfying the Web contract and ephemeral-runtime rule.

The initial implementation may prefer system Chromium/ChromeDriver because it is naturally available in the Alpine ecosystem used by Home Assistant, but this is an implementation choice rather than a permanent product dependency. Firefox or another suitable standards-compatible engine may replace it if HAOS evidence shows a cleaner or safer implementation.

Changing browser engine must not change the MCP Web contract.

## 8. SSH target

An SSH target owns host, port, user, host-key trust and credentials.

SSH access is deliberately bounded. The Bridge does not expose a default unrestricted shell such as `ssh_exec(command: string)`.

Each enabled SSH capability defines a fixed executable/command structure with only explicitly variable argument positions. Caller input cannot replace the host, user, credential or whole command.

Host-key verification is mandatory. Arguments are constructed without raw caller-controlled shell concatenation. Execution time and stdout/stderr size are bounded.

## 9. MCP server boundary

The Bridge exposes standard MCP tools over **Streamable HTTP**.

The MCP endpoint uses one Bridge-owned opaque Bearer credential in the initial product:

- generated by the application;
- displayed only once when issued/replaced;
- not recoverable later in clear text;
- revocable and replaceable from the administration UI;
- stored only as a verifier.

The Bridge deliberately does not create per-client business permissions. Possession of the Bridge credential grants access to the currently exposed Bridge tools. Fine-grained operational authorization belongs elsewhere when needed.

Compatibility with Agent Control Plane is achieved through ordinary MCP only.

## 10. Safety rules

Every adapter fails closed outside its configured technical envelope.

At minimum:

- caller input cannot replace target identity or credentials;
- secrets never appear in tool schemas, browser snapshots, logs or returned errors;
- execution/session duration and returned data are bounded;
- Web navigation cannot escape configured allowed origins;
- Web actions use Bridge-issued references from the current page snapshot rather than unrestricted caller selectors;
- SSH input cannot become a caller-controlled whole shell command;
- no automatic replay/retry of target operations after ambiguous failure or restart;
- disabled/invalid targets/tools are not exposed as usable MCP tools.

MCP annotations are descriptive only, never authorization.

## 11. Persistence

Persistence exists for Bridge-owned configuration only.

Durable state includes targets, bounded SSH capability definitions, encrypted target credentials/secrets, Web authentication setup, Bridge settings and the MCP credential verifier.

The Bridge does not persist ACP jobs/tasks, Execution Plane reasoning state, browser profiles/sessions/history, SSH runtime sessions or a permanent invocation history.

After the production-data preservation cutoff, supported configuration must be preserved through deterministic tested migrations.

## 12. Concurrency and retry behavior

The Bridge may serve multiple MCP clients and uses bounded in-memory concurrency limits to protect HAOS resources.

It has no durable invocation queue or scheduler. When capacity is exhausted, a new operation fails immediately with a bounded busy error.

No automatic logical retry is performed by default. The caller decides whether another attempt is appropriate.

## 13. HAOS application requirements

MCP Capability Bridge is a normal **Home Assistant OS App** with:

- least-privilege AppArmor;
- Home Assistant Ingress administration UI;
- user-configurable MCP server host port through HAOS Network settings;
- graphical language consistent with Agent Control Plane;
- French/English UI with in-UI language switch;
- light/dark mode with in-UI theme switch;
- `MCP Capability Bridge vX.Y.Z` in the header;
- configuration/visibility for Bridge state, MCP credential, targets, Web sessions/state where useful and SSH capabilities;
- dedicated logo and icon;
- complete English and French documentation.

Internal framework, exact browser engine, database schema, process topology and AppArmor rule details are technical choices unless they change visible behavior or the security boundary.

## 14. Observability

Ingress exposes only information required to configure and diagnose the Bridge: App/MCP state, target/tool availability, current bounded session/invocation counts, safe recent technical status and credential state.

It does not become a second Control Plane audit system or permanent business invocation history.

## 15. Non-goals

MCP Capability Bridge must not:

- run a reasoning model;
- own tasks, jobs, leases, reports, schedules, triggers or events;
- copy ACP identities/permissions or task authorization;
- create a generic workflow engine or durable invocation queue;
- interpret tool results as business decisions;
- require model-specific browser integration;
- persist reusable browser/SSH runtime sessions;
- expose unrestricted browser control, unrestricted SSH shell or arbitrary URL proxy;
- contain appliance-specific core logic;
- require Agent Control Plane or Agent Execution Plane.

## 16. Genericity test

A feature belongs in MCP Capability Bridge only if it is required to:

> configure bounded technical access to a non-MCP target, expose that access through standard MCP tools, execute it safely, and return the technical result.

If it instead decides what work should happen, reasons about the work, or decides which business actor/job is authorized to use the tool, it belongs elsewhere.

## 17. Delivery discipline

Implementation follows the suite lifecycle:

`planned -> implemented by Codex -> independently reviewed -> CI validated -> deployed on HAOS -> real acceptance tested -> accepted`

Codex implements only the current bounded lot. Its summary alone never marks a lot accepted. Any architectural drift or defect is corrected through a focused patch and re-reviewed before HAOS acceptance.
