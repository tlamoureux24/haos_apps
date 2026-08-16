# MCP Capability Bridge — Foundational Project Brief

Status: **foundational brief — detailed design not yet started**.

This document defines the product boundary for MCP Capability Bridge before implementation planning begins. It intentionally describes responsibilities, constraints and open questions without prematurely selecting the detailed adapter model or version-one feature set.

The root `ARCHITECTURE_CHARTER.md` is normative for this project.

## 1. Product purpose

MCP Capability Bridge is a generic MCP server that turns deliberately bounded non-MCP technical capabilities into MCP tools.

Its purpose is to make systems that do not natively speak MCP available through a standard MCP capability boundary without teaching reasoning clients or Agent Control Plane how SSH, target HTTP APIs, browser automation or appliance-specific transports work.

A concise product model is:

`configured technical target -> bounded adapter capability -> MCP tool -> compatible MCP client`

## 2. Primary goals

MCP Capability Bridge should eventually provide:

- a generic adapter architecture for non-MCP technical capabilities;
- MCP-native tool schemas and normalized results;
- explicit administrator configuration of targets and credentials;
- strict capability bounding, validation, limits and timeouts;
- safe secret storage and non-disclosure;
- independent usefulness with any compatible MCP client;
- HAOS packaging suitable for always-on local operation;
- clean interoperability with Agent Control Plane without depending on it.

Candidate adapter families include SSH, HTTP and browser automation. Their exact initial scope must be decided during detailed design rather than assumed by this brief.

## 3. Non-goals

MCP Capability Bridge must not:

- own reasoning models or model-provider credentials;
- run agent reasoning loops;
- own WorkSources, jobs, job leases or result/report lifecycles;
- own event intake, triggers, schedules or task definitions;
- duplicate Agent Control Plane identities or operational authorization policy;
- decide which agent may use which capability for which business scenario;
- become a general-purpose workflow engine;
- become a second Control Plane;
- require Agent Control Plane or Agent Execution Plane in order to run;
- expose unrestricted technical primitives merely because another component may later restrict their use.

## 4. Independence requirement

A standalone MCP Capability Bridge must be usable by any compatible MCP client that is appropriately configured and authenticated.

Agent Control Plane is an important expected client because it can govern Bridge tools through its existing deny-by-default task/capability model, but the Bridge must not encode Control Plane-specific task, identity, lease or report semantics.

Likewise, Agent Control Plane must not need Bridge-specific code. It should see the Bridge exactly as another administrator-configured MCP server.

## 5. Core separation rule

The central responsibility split is:

> **MCP Capability Bridge defines the maximum technical capability; Agent Control Plane defines the operational authorization.**

This has two consequences.

First, the Bridge must expose only technical operations that are intentionally bounded enough to be safe as capabilities in their own right. It must not rely on a downstream policy layer to rescue an intrinsically unlimited primitive.

Second, when Agent Control Plane is used, the Bridge must not recreate business authorization such as task membership, per-job capability selection or agent-specific operational policy. Those decisions remain Control Plane responsibilities.

## 6. Capability model direction

A Bridge capability should have an explicit MCP-facing contract including at least:

- stable tool identity;
- human-readable purpose;
- strict input schema;
- bounded target/configuration context;
- deterministic validation before execution;
- explicit timeout/resource limits;
- bounded and normalized result handling;
- redaction rules for secrets and sensitive target data where applicable.

The detailed capability-definition format remains open.

Capability design should prefer narrow, intention-revealing operations over generic command passthrough. A raw primitive such as:

`ssh_exec(command: string)`

must not become the default architecture simply because it is easy to implement. If a deliberately broad primitive is ever supported, its scope, threat model, configuration and operational limits must be an explicit product decision.

## 7. Adapter direction

Target-specific mechanics belong behind adapter interfaces.

Potential adapter families include:

- **SSH** for explicitly configured remote-command or subsystem capabilities;
- **HTTP** for bounded requests to configured endpoints/APIs;
- **Browser** for controlled browser automation where no adequate API exists.

The generic core should understand capability definitions, invocation lifecycle, limits and MCP contracts. It should not contain growing branches for individual products such as OpenDTU, Cerbo GX, UniFi or other appliances.

Product-specific behavior, when genuinely necessary, must be expressed through administrator configuration or a bounded adapter/plugin implementation rather than contaminating the core architecture.

## 8. SSH direction

If SSH is included, detailed design must address at least:

- target identity and host-key verification;
- credentials/keys and rotation;
- allowed remote account and privilege model;
- whether capabilities map to fixed commands, argument templates, subsystems or another bounded representation;
- command/argument validation and quoting;
- execution timeout and output-size limits;
- exit status and normalized error handling;
- prevention of arbitrary host/user/key override by MCP arguments;
- prevention of accidental shell expansion outside the intended capability envelope.

The preferred security model is expected to combine a restricted remote account with a restricted Bridge-side capability definition rather than relying on either layer alone.

## 9. HTTP direction

If HTTP is included, detailed design must address at least:

- configured base targets and endpoint bounding;
- allowed methods;
- headers and credential injection;
- argument-to-path/query/body mapping;
- redirects;
- DNS/IP changes and SSRF considerations;
- TLS verification;
- timeouts and response-size limits;
- content-type handling;
- safe result normalization;
- prevention of MCP arguments changing the configured origin or secret material.

The generic HTTP adapter must not become an unrestricted network proxy.

## 10. Browser direction

If browser automation is included, detailed design must address at least:

- browser engine/process isolation;
- persistent versus ephemeral sessions;
- authentication/session credential ownership;
- navigation-origin restrictions;
- download/upload behavior;
- DOM/page-content size limits;
- JavaScript execution boundaries;
- screenshot and artifact handling;
- timeouts and stuck-page recovery;
- prompt-injection/untrusted-page-content considerations;
- how capabilities remain bounded instead of becoming unrestricted remote browser control.

Browser automation is expected to be the most security-sensitive adapter family and should not be included in the first implementation merely for completeness if its threat model is not ready.

## 11. Credential ownership

The Bridge owns credentials it directly needs to access its configured technical targets, including where applicable:

- SSH private keys or equivalent authentication material;
- HTTP/API credentials;
- browser-session credentials or secrets.

These secrets must not be copied into Agent Control Plane or Agent Execution Plane merely to make integration convenient.

MCP clients should receive only tool contracts and sanitized results, not target credentials, private keys, session cookies or hidden connection configuration.

Credential storage, one-time display behavior, rotation, deletion and backup implications must be designed before production use.

## 12. Target and configuration ownership

The Bridge owns the technical target definition needed for its adapter to operate.

MCP invocation arguments must not be able to silently replace administrator-controlled values such as:

- SSH host, port, user or key;
- HTTP origin/base URL or secret headers;
- browser target origin or stored session identity.

Administrator-fixed context should remain outside the model-visible schema whenever practical, or otherwise be validated against an immutable configured envelope before execution.

This complements — but does not duplicate — Agent Control Plane's `fixed_arguments_v1` capability narrowing when Control Plane is in the path.

## 13. MCP server boundary

The Bridge should present capabilities through standard MCP contracts and should avoid private coupling to one client implementation.

Detailed design must decide:

- supported MCP transport(s);
- server authentication;
- MCP protocol-version support;
- initialization and tool discovery behavior;
- schema limits;
- result-size limits;
- cancellation and timeout mapping;
- whether capability inventory changes require stable fingerprints or other compatibility signals for clients such as Agent Control Plane.

Compatibility with Agent Control Plane's connector discovery/fingerprint model is an important acceptance target, but must be achieved through ordinary MCP behavior rather than a private back channel.

## 14. Authorization boundary

The Bridge needs sufficient administration security to protect its own configuration and MCP endpoint, but it must not invent Control Plane-style operational task authorization.

When used behind Agent Control Plane:

- Bridge configuration defines which technical capabilities exist;
- Control Plane task revisions select which of those capabilities are exposed to a given governed execution;
- Control Plane may further narrow arguments through its own generic mechanisms;
- Bridge still validates every invocation against its own technical capability definition.

Neither layer should broaden the other.

When used standalone, the administrator assumes responsibility for deciding which clients are allowed to access the Bridge and which configured capabilities they can discover/use according to the standalone access model that will be designed later.

## 15. Execution lifecycle and retries

The Bridge owns the lifecycle of an individual technical capability invocation that it performs directly.

Detailed design must define:

- invocation timeout;
- cancellation;
- subprocess/session cleanup;
- transport retry policy, if any;
- which operations are safe to retry;
- output collection and truncation;
- normalized success/failure results;
- crash/restart behavior for in-flight invocations.

The Bridge must not blindly retry side-effecting operations. Retry behavior should be capability-/adapter-aware and must not conflict with retries owned by Agent Execution Plane or Agent Control Plane.

## 16. Persistence direction

Persistence requirements are deliberately undecided at brief stage.

The detailed design must determine what must be stored durably, potentially including:

- target definitions;
- capability definitions;
- adapter configuration;
- credentials/secrets;
- browser-session state where supported;
- administrator settings;
- bounded diagnostic history.

The Bridge must not persist copies of Control Plane tasks/jobs or Execution Plane reasoning state.

The production-data preservation cutoff must be declared before users are asked to create non-disposable production target/capability configuration.

## 17. Observability direction

The Bridge needs enough observability to operate technical adapters safely without becoming a duplicate governance audit system.

Potential areas include:

- adapter/target health;
- capability availability;
- current invocation counts;
- bounded duration/result statistics;
- normalized transport/target failures;
- redacted administration logs;
- configuration-change traceability appropriate to the Bridge itself.

When Agent Control Plane is present, its audit remains the authoritative record of governed operational authorization and job-context invocation decisions. Bridge diagnostics should complement that record, not duplicate its semantics.

## 18. Security baseline

The detailed plan must include at least:

- least-privilege HAOS runtime and AppArmor policy;
- minimal listener and outbound-network exposure;
- strong administrator and MCP endpoint authentication appropriate to the final design;
- strict target bounding and SSRF resistance where relevant;
- host-key/TLS verification appropriate to the adapter;
- secret non-disclosure and redaction;
- bounded input/output sizes;
- bounded execution duration and concurrency;
- cleanup of subprocesses/browser sessions;
- no target/credential override from model-controlled input;
- fail-closed behavior when configured capability validity cannot be proven.

## 19. Genericity tests

A proposed core feature should be rejected or moved behind an adapter/configuration layer if it requires:

- `if control_plane` in core capability execution;
- `if execution_plane` in core capability execution;
- `if opendtu`, `if cerbo`, `if unifi` or other appliance-specific branches in the generic core;
- interpreting one client's task/job semantics;
- running a model or reasoning loop;
- deciding operational authorization based on agent identity or business scenario.

The core should understand adapters, targets, bounded capabilities and MCP — not agents, jobs or products.

## 20. Initial integration target

A likely first suite integration scenario is:

`Agent Execution Plane -> governed MCP surface from Agent Control Plane -> MCP Capability Bridge -> bounded SSH/HTTP/browser capability -> target system`

For Agent Control Plane, however, MCP Capability Bridge must look like an ordinary upstream MCP server.

A standalone Bridge scenario must remain equally valid:

`any compatible MCP client -> MCP Capability Bridge -> configured bounded target capability`

## 21. Detailed-design questions to resolve later

Before substantial implementation begins, the detailed design must explicitly settle at least:

1. the adapter interface and capability-definition model;
2. which adapter family/families belong in the first accepted release;
3. MCP transport, authentication and protocol compatibility;
4. target configuration and credential lifecycle;
5. capability schema/fingerprint stability;
6. invocation concurrency, timeout, cancellation and cleanup;
7. safe retry semantics;
8. SSRF/network policy and target verification;
9. SSH capability bounding if SSH is included;
10. HTTP request bounding if HTTP is included;
11. browser isolation/session/security model if Browser is included;
12. local persistence and production-data cutoff;
13. administration UX and observability;
14. HAOS listener/network/AppArmor boundaries;
15. CI and real-HAOS acceptance gates;
16. interoperability acceptance against Agent Control Plane using only standard MCP contracts.

These questions are intentionally deferred while Agent Execution Plane receives the next detailed design focus.

## 22. Delivery discipline

MCP Capability Bridge will follow the suite delivery lifecycle defined in `ARCHITECTURE_CHARTER.md`.

Its authoritative implementation plan will be created only after its detailed architecture is agreed. Until then, Codex should not be asked to invent adapter contracts or security boundaries through implementation.
