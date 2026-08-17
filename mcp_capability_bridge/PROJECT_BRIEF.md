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

The product is not permanently limited to the adapters implemented in its first release. The generic MCP/authentication/configuration core must allow later target types to be added as separate bounded adapters without redesigning unrelated adapters or coupling the Bridge to a particular client.

The first implementation focuses only on the two concrete classes of local technical access currently required:

- **Web administration interfaces**, reached through HTTP or HTTPS and operated through a real browser engine;
- **SSH targets**, reached through deliberately bounded configured commands.

These are the **initial adapters**, not the architectural limit of the Bridge.

Future needs may justify additional adapters — for example FTP/SFTP, a direct bounded API adapter, another remote-management protocol or another technical transport. Such examples are intentionally **not part of the current implementation plan**. Each future adapter must be designed and accepted as its own bounded extension while preserving the common Bridge security and MCP contract.

## 4. Responsibility split

The key separation rule remains:

> **MCP Capability Bridge defines the maximum technical capability; Agent Control Plane, when present, defines operational authorization.**

The Bridge owns:

- technical target connection configuration;
- target credentials it directly needs;
- the adapter-specific MCP tool surface;
- strict argument and target-envelope validation;
- technical invocation/session timeout and resource limits;
- adapter execution and cleanup;
- bounded result normalization and secret redaction;
- the MCP server endpoint itself.

The Bridge does not own:

- agents or models;
- model-provider credentials;
- tasks, jobs, leases, reports or reasoning state;
- schedules, triggers or event routing;
- Control Plane identities or per-business-scenario authorization;
- decisions about which job should receive which tool.

## 5. Web administration target — intended behavior

A Web target represents an administrator-configured **HTTP/HTTPS administration interface**.

The objective is not to encode a pre-written workflow for each website. The objective is to let a reasoning model **interactively inspect and operate the configured web interface** through ordinary MCP tool calls.

The Bridge therefore drives the browser. The model does not need a native browser feature: it only needs ordinary tool/function-calling support from its host.

A Web target owns at least:

- its fixed base origin and any explicitly allowed same-target origins;
- TLS policy;
- authentication/session material that the Bridge itself needs;
- browser/session limits;
- enabled/disabled state.

For an enabled valid Web target, the Bridge exposes a deterministic target-scoped browser tool family sufficient for interactive administration, including operations equivalent to:

- start/open a browser session on the configured target;
- inspect the current page as a bounded textual/accessibility snapshot with stable element references;
- navigate only within the configured allowed origin envelope;
- click a referenced element;
- fill a referenced field;
- select a referenced option;
- send a bounded key/submit action where needed;
- wait for bounded page/state changes;
- optionally obtain a screenshot when useful and supported by the consuming client/model path;
- close the browser session.

The exact MCP tool names are technical design, but the behavior must remain generic and target-scoped.

The model must **not** be allowed to supply an arbitrary external URL, arbitrary JavaScript, unrestricted DOM selectors, DevTools commands, filesystem paths, downloads/uploads or browser credentials.

Browser authentication secrets belong to the Bridge. Where an interface needs login, the Bridge must be able to establish the configured authenticated session without revealing stored credentials to the model/MCP client.

## 6. Model-side requirement for Web access

Web access must not require a model-specific browser integration.

A compatible reasoning host only needs to:

- discover ordinary MCP tools;
- expose them through the model provider's tool/function-calling mechanism;
- feed the bounded tool results back to the model.

The primary page representation returned to the model is textual/structured so a non-vision model can operate the interface. Screenshot support is supplementary, not a requirement for basic Web administration.

## 7. SSH target — intended behavior

An SSH target owns host, port, user, host-key trust and credentials.

SSH access is deliberately bounded. The Bridge does not expose a default unrestricted shell such as `ssh_exec(command: string)`.

Each enabled SSH capability defines a fixed executable/command structure with only explicitly variable argument positions. Caller input cannot replace the host, user, credential or whole command.

Host-key verification is mandatory. Arguments are constructed without raw caller-controlled shell concatenation. Execution time and stdout/stderr size are bounded.

## 8. MCP server boundary

The Bridge exposes standard MCP tools over **Streamable HTTP**.

The MCP endpoint is authenticated with one Bridge-owned opaque Bearer credential in the initial product:

- generated by the application;
- displayed only once when issued/replaced;
- not recoverable later in clear text;
- revocable and replaceable from the administration UI;
- stored only as a verifier because the Bridge only needs to validate it.

This credential authenticates the Bridge endpoint as a whole. MCP Capability Bridge deliberately does **not** create a second per-client identity/permission system. A directly connected client that possesses the credential can discover/use the currently exposed Bridge tools.

Fine-grained operational authorization belongs to a governing MCP client such as Agent Control Plane when required.

Compatibility with Agent Control Plane is an acceptance target achieved through standard MCP only, never through a private integration mode.

## 9. Target safety rules

Every adapter must fail closed outside its configured technical envelope.

At minimum:

- caller input cannot replace administrator-controlled target identity or credentials;
- secrets never appear in tool schemas, browser snapshots, logs or returned errors;
- execution/session duration and returned data are bounded;
- adapter-specific escape paths are blocked by that adapter's configured envelope;
- Web navigation cannot escape the configured origin envelope;
- Web actions operate on references obtained from the current bounded page snapshot rather than accepting unrestricted caller selectors;
- SSH arguments cannot become a caller-controlled whole shell command;
- no automatic replay/retry of target operations after an ambiguous failure or restart;
- disabled or invalid targets/tools are not exposed as usable MCP tools.

MCP tool annotations may describe behavior but are not an authorization mechanism.

## 10. Browser session behavior

Interactive web use spans several MCP calls, so the Bridge may maintain **short-lived in-memory browser sessions**.

A session is:

- created for one configured Web target;
- identified by an opaque runtime handle returned to the caller;
- usable only with that same target's tool family;
- bounded by inactivity/absolute lifetime and resource limits;
- cleaned up on explicit close, timeout, error, App shutdown or restart;
- never a durable job or browser-history database.

Browser sessions are not replayed or restored after an App restart.

## 11. Persistence

Persistence exists for Bridge configuration, not for Control Plane or Execution Plane state.

Durable state includes only what the Bridge itself owns, such as:

- target definitions and adapter type;
- adapter-owned bounded capability/configuration definitions where applicable;
- encrypted target credentials/secrets;
- Web authentication/session setup configuration where required;
- Bridge settings;
- MCP credential verifier.

The Bridge does not persist ACP tasks/jobs, Execution Plane reasoning/model state, permanent browser histories or a permanent history of tool invocations.

Once the Bridge reaches its production-data preservation cutoff, Bridge-owned target/adapter configuration becomes non-disposable and later schema changes must preserve supported data through tested upgrades.

## 12. Invocation and concurrency behavior

MCP Capability Bridge may serve multiple MCP clients and does not adopt Execution Plane's one-job execution model.

Individual adapter invocations and stateful adapter sessions are technically bounded. The implementation may use bounded global and adapter-specific concurrency limits to protect the HAOS host, but it must not create a waiting job system, scheduler or durable invocation queue.

When capacity is exhausted, a new operation fails immediately with a bounded busy error. No automatic invocation retry is performed by default; the caller decides what to do next.

## 13. Administration and HAOS application requirements

MCP Capability Bridge is delivered as a normal **Home Assistant OS App** and follows the same practical App discipline as Agent Control Plane and Agent Execution Plane.

Visible product requirements are:

- installable and runnable from the repository as a normal HAOS App;
- a mandatory least-privilege **AppArmor profile** appropriate to the actual adapters/runtime;
- a Home Assistant **Ingress administration interface**;
- a user-configurable **MCP server host port** through the HAOS App Network configuration;
- an administration UI visually consistent with Agent Control Plane's graphical language and interaction style while remaining specific to Bridge responsibilities;
- a fully bilingual **French/English** UI with an in-UI language switch;
- full **light/dark mode** support with an in-UI theme switch;
- the header displays **MCP Capability Bridge** with the running **version immediately beside the product name**;
- generic target management plus adapter-specific configuration/status views for the adapters currently installed by the App;
- dedicated repository **logo** and **icon**;
- complete user documentation in **English and French**, including installation, MCP connection, current adapter setup, security constraints and examples.

Internal framework, database schema, exact process topology, AppArmor rule details, implementation libraries and the internal adapter-registration mechanism are technical choices unless they change these visible/security requirements.

## 14. Observability

The Ingress UI exposes only operational information needed to configure and diagnose the Bridge, such as:

- App/MCP server state;
- target/tool availability;
- current bounded invocation/session counts;
- last useful redacted technical failure/status;
- credential presence/rotation state.

It does not become a second Control Plane audit system or permanent business invocation history.

## 15. Security baseline

The implementation must preserve:

- unprivileged HAOS runtime;
- least-privilege AppArmor;
- authenticated MCP endpoint;
- protected reversible target secrets and non-reversible MCP credential verification;
- strict input bounds;
- adapter-controlled target-envelope validation;
- adapter-appropriate peer/server verification;
- output/time/concurrency limits;
- secret redaction/non-disclosure;
- deterministic subprocess/session cleanup where relevant;
- no model-controlled configuration mutation;
- fail-closed behavior when a target/tool definition is invalid or its technical envelope cannot be proven.

## 16. Non-goals

MCP Capability Bridge must not:

- run a reasoning model;
- own tasks, jobs, leases, reports, schedules, triggers or events;
- copy ACP identities/permissions or task authorization;
- create a generic workflow engine;
- create a durable invocation queue;
- interpret tool results as business decisions;
- require a model-specific browser integration;
- expose unrestricted passthrough primitives merely because another component may later restrict them;
- contain appliance-specific core logic;
- require Agent Control Plane or Agent Execution Plane.

## 17. Adapter extensibility rule

A new technical transport belongs as a new Bridge adapter when it can define:

- administrator-controlled target configuration and credentials;
- a bounded MCP tool surface;
- strict validation preventing caller-controlled escape from that target envelope;
- bounded execution/result/resource behavior;
- deterministic cleanup and safe failure semantics appropriate to that transport.

Adding such an adapter must not require redesigning MCP authentication, Control Plane integration, Execution Plane integration or unrelated adapters.

## 18. Genericity test

A feature belongs in MCP Capability Bridge only if it is required to:

> configure bounded technical access to a non-MCP target, expose that access through standard MCP tools, execute it safely, and return the technical result.

If it instead decides what work should happen, reasons about the work, or decides which business actor/job is authorized to use the tool, it belongs elsewhere.

## 19. Delivery discipline

Implementation follows the suite lifecycle:

`planned -> implemented by Codex -> independently reviewed -> CI validated -> deployed on HAOS -> real acceptance tested -> accepted`

Codex implements only the current bounded lot. Its summary alone never marks a lot accepted. Any architectural drift or defect is corrected through a focused patch and re-reviewed before HAOS acceptance.
