# MCP Capability Bridge — Project Brief

Status: **revised product boundary — authoritative before implementation**.

This document defines the product purpose and visible guarantees of MCP Capability Bridge. `ARCHITECTURE_CHARTER.md` remains normative. `TECHNICAL_DESIGN.md`, `THREAT_MODEL.md` and `IMPLEMENTATION_PLAN.md` refine this brief without expanding the Bridge into a reasoning engine, task system or business control plane.

## 1. Product purpose

MCP Capability Bridge is an independent, generic MCP server that turns deliberately configured access to non-MCP technical systems into bounded MCP capabilities.

Its responsibility is to let an administrator configure technical targets and their credentials, define technical capabilities, publish selected capabilities into isolated MCP client namespaces, validate and execute calls through the owning adapter, and return bounded results with known Bridge secrets removed.

Conceptually:

`configured target -> bounded adapter capability -> client namespace -> MCP -> compatible client`

The Bridge is not a model runtime, task system, scheduler, durable queue, workflow engine or business authorization system.

## 2. Independent use and suite use

The Bridge must remain fully useful without Agent Control Plane or Agent Execution Plane.

In standalone use, an administrator creates an MCP client namespace, publishes selected Bridge capabilities to it and gives that client its one-time Bearer credential.

In suite use:

`technical target -> Bridge -> ordinary MCP connector -> ACP -> authorized task envelope -> AEP`

ACP connects with a normal Bridge namespace credential, discovers only the capabilities published to that namespace and governs which of them a task may use. AEP receives task-scoped virtual capabilities through ACP's existing MCP boundary. The Bridge has no ACP-specific endpoint, database access, job contract or back channel.

An AEP standalone execution or any other MCP client may connect directly through the same standard MCP surface.

## 3. Adapter-oriented product model

The Bridge is modular from its first implementation.

The generic core owns MCP transport, MCP client namespaces, authentication, target storage, secret protection, adapter registration, shared concurrency, safe status and administration. An adapter owns one technical target family and supplies its configuration validation, MCP tool definitions, invocation implementation, cleanup and safe status metadata.

The first built-in adapters are:

- **SSH**, exposing administrator-defined bounded command capabilities;
- **Web interactive**, exposing short-lived browser sessions for configured administration interfaces.

Future releases may add built-in adapters such as bounded HTTP/API, SFTP or another justified technical transport without redesigning the core or unrelated adapters.

Version one does not load third-party executable plugins at runtime. “Adapter” means a statically packaged, reviewed module registered through an internal interface. This preserves reproducible HAOS images and a provable AppArmor boundary.

## 4. Responsibility boundary

> **The Bridge defines and enforces maximum technical capability. ACP, when present, further restricts operational use for each task.**

The Bridge owns target connection details and credentials, technical client namespaces, capability publication, adapter validation/execution, runtime resource lifecycle, bounds, known-secret redaction and MCP results.

The Bridge does not own prompts, models, reasoning, events, tasks, jobs, leases, schedules, reports, ACP identities, business policies or decisions about why work should run.

Namespace publication is technical exposure, not a policy language. It answers only “which maximum Bridge capabilities may this MCP client see?” ACP may impose a narrower task-specific envelope.

## 5. MCP client namespaces

Multiple independent MCP clients are supported from the first authenticated release.

Each namespace has:

- a stable internal ID and administrator-facing name;
- an active, revoked or archived lifecycle;
- its own opaque Bearer credential lifecycle;
- an explicit set of published Bridge capabilities;
- independent Web sessions, quotas and safe status;
- no access to handles or state owned by another namespace.

One clear token is displayed only once on initial issue or rotation. Only a fast one-way verifier is stored. Rotation immediately invalidates the previous credential and closes the namespace's active Web sessions. Revocation removes all MCP access and closes those sessions. Archiving is presentation-only and allowed only after revocation; it never deletes historical references.

Namespaces do not contain business roles or task policies. Two namespaces may receive the same capability. Tool discovery remains isolated by authentication.

## 6. Target and capability publication

Targets are administrator-owned and have stable IDs and bounded human-readable keys. Target secrets never enter MCP schemas.

Only enabled, statically valid capabilities of enabled targets may be published. A namespace sees only capabilities explicitly assigned to it. Disabling or invalidating a target removes its tools from discovery and emits the standard MCP tool-list change notification where supported.

Tool names and schemas are deterministic and compatible with current ACP connector constraints. A configuration change that changes an input schema changes its fingerprint so ACP can fail closed for immutable task revisions.

## 7. SSH adapter

An SSH target fixes host or IP, port, username, authentication material and an explicitly confirmed host key.

The adapter never exposes a generic caller-controlled shell command. The administrator creates named capabilities such as `nas_disk_usage` or `service_status`. Each capability fixes one target, an absolute command head, an ordered sequence of fixed and typed caller-supplied argument tokens, a strict object schema, and timeout/output bounds.

Version one supports a documented POSIX remote-command environment. Every token is independently validated and quoted for that environment; shell operators, caller-controlled command heads, PTYs, arbitrary environment maps, unrestricted stdin, forwarding and connection reuse are excluded.

Every invocation opens a fresh SSH connection, verifies the pinned host key, executes one capability and closes all resources. There is no automatic retry.

## 8. Web interactive adapter

A Web target represents one configured HTTP/HTTPS administration interface and one configured target account.

The maximum authority of a Web target is the authority of that account within the configured network/origin envelope:

- a read-only account limits the model to what that account can read;
- an operator account permits its operator actions;
- an administrator account may permit every action visible to that administrator.

The Bridge and ACP cannot infer the business meaning of an arbitrary button. Publishing an interactive Web capability therefore authorizes use of the browser primitives within the account's actual rights. The administration UI must present this consequence clearly and recommend dedicated least-privilege accounts.

Each enabled Web target exposes a deterministic target-scoped family equivalent to open, snapshot, navigate, click, fill, select, press, wait and close.

Screenshots are outside the initial interactive contract. They may be designed later only with an explicit sensitivity and client-compatibility contract.

The model cannot supply browser credentials, arbitrary selectors, JavaScript, DevTools commands, filesystem paths, uploads, downloads or unrestricted external URLs.

## 9. Web session isolation

Every Web open creates a clean, memory-owned session bound to exactly one namespace and one target.

The session uses a new temporary browser profile, never imports prior state, has cryptographically random handles, accepts only one in-flight action, has inactivity and absolute limits, and is destroyed on close, expiry, credential rotation/revocation, emergency target invalidation, browser failure, shutdown or restart. Ordinary target mutation remains refused while a session is active.

No reusable browser state is written under persistent storage. Handles from one namespace are invalid in every other namespace, even when both namespaces can access the same target.

## 10. Web network and action envelope

The administrator fixes the base origin and explicitly confirms every additional navigation, authentication and resource origin required by the target.

The adapter fails closed for unapproved top-level navigation, frames, popups, WebSockets, redirects and resource requests. Local/private destinations are allowed only when part of the administrator-confirmed target envelope; arbitrary discovery of the HAOS host or local network is prohibited.

Dangerous schemes, downloads, uploads, extra windows and browser filesystem access are disabled initially. Target credentials are injected only into the configured authentication flow and never into unrelated origins.

Element references belong to one snapshot generation. Every action revalidates the referenced element and then invalidates all references. Concurrent or stale actions fail and require a new snapshot.

## 11. Result and sensitivity contract

Results are bounded MCP structured content with compatible text where required.

The Bridge guarantees removal of secrets it owns or injected, including target passwords, private keys, Bearer tokens, cookies and authorization headers. Password/hidden inputs and known sensitive DOM values are omitted from textual snapshots.

Arbitrary target output may itself contain operationally sensitive information unknown to the Bridge. The UI and documentation must state this honestly. Results are not persisted as Bridge invocation history, but another component may persist its own derived result according to its contract.

For actions with ambiguous delivery, results and errors expose whether a target effect may already have occurred. The Bridge never automatically replays Web actions or SSH commands.

## 12. Runtime, persistence and concurrency

Configuration is durable; execution state is disposable.

Durable data includes namespaces, credential verifiers, targets, encrypted target secrets, SSH capabilities, Web configuration, publication mappings and the latest 500 payload-free operational Activity events.

The Bridge does not persist browser profiles, Web sessions, SSH connections,
MCP arguments, page snapshots, command output or business results. Activity is
a bounded metadata journal, not a replay queue or result history.

Global, per-adapter, per-target and per-namespace limits protect HAOS. Capacity
exhaustion fails immediately with a bounded busy error; there is no durable or
implicit in-memory execution queue. MCP request bodies above 256 KiB are
refused before protocol parsing.

Administration and MCP execution share one authoritative runtime so active-use locks, credential rotation, session counts and shutdown cannot diverge across process-local memory.

## 13. Security and failure rules

At minimum:

- authentication is required for all MCP discovery and calls;
- namespaces cannot observe or use one another's state;
- caller input cannot replace a target, account, credential or SSH command head;
- target operations never retry automatically;
- cancellation and lost responses never synthesize success;
- target mutation or secret rotation is refused while an operation is active;
- known secrets do not appear in schemas, normal logs, returned errors or snapshots;
- disabled, invalid or unpublished capabilities are not callable even if their old names are known;
- MCP annotations are descriptive only;
- the Bridge remains secure without ACP.

## 14. Administration UI and HAOS identity

MCP Capability Bridge is a normal Home Assistant OS App with an Ingress-only administration surface.

It must look and behave like a member of the same suite as ACP and AEP. Reuse established conventions rather than approximate them independently:

- committed `icon.png` and `logo.png` remain authoritative;
- header icon, product name and `vX.Y.Z` placement;
- navigation geometry, typography, cards, status colors and spacing;
- `pagehead split` with primary actions at the top right;
- shared right-side drawer, overlay, close button, outside click, `Esc`, focus handling and mobile behavior;
- one-time secret acknowledgement pattern;
- archived-item filters where applicable;
- immediate refresh and bounded polling only for active dynamic views;
- FR/EN switching for static and dynamic text;
- light/dark mode;
- stable scrollbar gutter so view and drawer changes never shift the UI horizontally.

Primary views cover Overview, MCP clients, Targets, SSH capabilities, Web targets/sessions and MCP access. The Bridge does not reproduce ACP jobs, reports or audit cockpit.

## 15. Observability

Ingress shows only safe operational information needed to configure and diagnose the Bridge: MCP readiness, namespace state, published counts, target validity, last explicit connectivity check, active bounded sessions/operations, and safe last-error codes/durations.

Live sessions and operation counters are memory-only. The Activity page keeps
at most 500 safe operational metadata events across restarts; there is no
permanent payload or business-result log.

## 16. HAOS and AppArmor

The App runs unprivileged with two isolated network surfaces:

- Ingress administration on container port 8099;
- authenticated MCP plus non-sensitive health endpoints on container port 8098, with configurable HAOS host mapping.

Both surfaces are hosted by one authoritative application runtime with separate route sets and security middleware.

AppArmor starts from observed executable and filesystem inventories. Each adapter adds only proven runtime paths. Browser acceptance requires unprivileged operation without broad host filesystem/device access.

## 17. Compatibility and data lifecycle

The first implementation targets the MCP protocol and Python SDK generation actually used by ACP at implementation time, with exact pins and contract tests against current ACP code.

Compatibility tests cover discovery, schemas, tool-name limits, tool-list changes, calls, errors, result bounds, redaction and the complete Bridge→ACP→AEP path.

Version 1.0.0 declares generation 1 as the production-data compatibility cutoff
after complete real-HAOS acceptance. Every later namespace, credential, target,
publication, Activity or capability schema change requires a deterministic
tested migration or a new explicitly documented generation.

## 18. Non-goals

The Bridge must not run a model, own tasks/jobs/business policies, load arbitrary third-party code at runtime in version one, expose unrestricted SSH commands, claim generic Web clicks are finer-grained than the configured account, persist runtime sessions, create a durable operation queue, require ACP/AEP or contain appliance-specific core behavior.

## 19. Delivery discipline

Implementation follows:

`planned -> implemented -> independently reviewed -> CI conformant -> deployed on HAOS -> real acceptance tested -> accepted`

Only the current bounded lot is implemented. Security contradictions return to design before code. A successful build or Codex summary is never production acceptance.
