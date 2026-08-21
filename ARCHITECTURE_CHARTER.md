# Three-Component Architecture Charter

Status: **foundational and normative** for Agent Control Plane, Agent Execution Plane and MCP Capability Bridge.

This charter defines the architectural boundaries shared by the three projects. It is deliberately more stable than any implementation plan. A feature or implementation choice that conflicts with this charter must be reconsidered before code is written.

## 1. Foundational invariant

Each component must remain fully usable independently of the other two and must implement only its own responsibility. Integration between components must occur exclusively through generic, documented contracts.

No component may be intentionally crippled to force installation of another component. No component may gain another component's responsibility merely because doing so is convenient for one integration scenario.

The three names are also responsibility tests:

- **Agent Control Plane** governs work and authorized capabilities.
- **Agent Execution Plane** performs model-driven reasoning and execution.
- **MCP Capability Bridge** exposes non-MCP technical capabilities through MCP.

If a proposed feature does not fit the responsibility expressed by the component name, its placement must be challenged before implementation.

## 2. Agent Control Plane

Agent Control Plane is the governance and work-control component.

Its responsibilities include:

- administrator-defined identities and credentials;
- MCP connector discovery and governed capability exposure;
- task definitions and immutable task revisions;
- event intake, mappings, triggers and schedules;
- durable jobs and execution leases;
- reports and audit state;
- deny-by-default enforcement of the exact capability envelope selected by the administrator;
- fail-closed behavior when that envelope can no longer be proven valid.

Agent Control Plane is model-neutral. It does not decide how a model reasons and does not own model-provider credentials.

Agent Control Plane must not contain SSH-, browser-, HTTP-target- or infrastructure-specific execution code merely to reach systems that do not expose MCP. Such capabilities belong in an MCP server, including MCP Capability Bridge when that project is used.

Agent Control Plane must remain useful with any compatible MCP client and any compatible upstream MCP server. Agent Execution Plane and MCP Capability Bridge are optional peers, not dependencies.

## 3. Agent Execution Plane

Agent Execution Plane is the reasoning and execution component.

Its responsibility is to take one source-supplied execution, reason about it through a configured model/reasoning provider, invoke only the source-authorized MCP operational capabilities made available to that execution, optionally use bounded provider-native reasoning/information helpers that remain inside the provider/runtime responsibility, and return a result through the source/result contract in use.

Its architecture must keep three mechanics separated without turning them into a generic orchestration framework:

- thin source/result boundaries;
- model/reasoning provider adapters, including any permitted provider-native reasoning/information helpers;
- MCP operational capability access.

Agent Control Plane is the reference source integration. A small documented standalone API provides independent use without Agent Control Plane. Additional source integrations may be added later only when concrete need exists; the charter does **not** require a generic WorkSource/plugin framework.

Agent Execution Plane must not become a second control plane. It does not own administrator task policy, operational authorization, event routing, trigger definitions, durable governance audit, or connector capability selection.

Agent Execution Plane may use provider-native facilities that support reasoning or external information retrieval, for example internal planning or public Web search, when they do not provide a path to operate the user's infrastructure, access AEP host/private data, obtain connector credentials, or bypass the source-defined MCP operational capability envelope.

Agent Execution Plane must not implement or permit direct SSH, local shell/filesystem control, browser automation against user infrastructure, vendor-specific HTTP control, native provider MCP connectors, or other infrastructure access as privileged side channels. Such operational capabilities must be presented to the execution engine through the source-authorized MCP path.

## 4. MCP Capability Bridge

MCP Capability Bridge is a generic MCP server that turns bounded non-MCP technical capabilities into MCP tools.

Candidate adapter families include SSH, HTTP and browser automation, but the supported set and version-one scope are implementation decisions rather than charter requirements.

The Bridge owns the technical connection configuration and credentials needed to reach its configured targets. It exposes only the technical capability surface deliberately defined by the administrator or adapter configuration.

The Bridge does not own agents, reasoning models, jobs, task definitions, triggers, schedules, Control Plane identities or operational authorization policy.

The Bridge must remain useful with any compatible MCP client. Agent Control Plane is one possible MCP client/governance layer, not a dependency.

A key separation rule is:

> **MCP Capability Bridge defines the maximum technical capability; Agent Control Plane defines the operational authorization.**

When both are used, the Bridge must not duplicate Control Plane task policy, and Control Plane must not learn Bridge-specific SSH/HTTP/browser implementation details.

## 5. Integration contracts

### 5.1 Execution source boundary

Agent Execution Plane receives an execution through a small explicit source boundary and returns the outcome through that source's documented result lifecycle.

Agent Control Plane is the reference integration; the standalone API is the independent generic boundary. Both must map to the same core execution semantics rather than create separate engines or business behavior.

Source-specific acquisition, lease, acknowledgement and retry mechanics stay at the boundary that owns them. They must not leak source-specific business logic into the execution core.

### 5.2 Operational MCP boundary and provider-native helpers

MCP is the **operational capability boundary** for model-initiated access to or actions on user-controlled infrastructure and other non-provider technical systems.

Agent Execution Plane must consume such operational capabilities through MCP rather than privileged implementation-specific back doors. Agent Control Plane may expose a governed MCP capability surface to it. MCP Capability Bridge may appear to Agent Control Plane, Agent Execution Plane in standalone use, or another MCP client exactly as an MCP server.

Provider-native reasoning/information helpers are a separate category. A provider adapter may expose facilities such as internal planning, bounded interaction mechanics or public Web search when those facilities serve the model's reasoning and do not themselves provide operational access to the user's infrastructure, AEP host/private filesystem, local network targets, connector credentials or an alternate MCP/connector path.

A provider-native helper does not become an ACP operational capability merely because the model can call it. Conversely, labeling a provider-native facility as a reasoning helper must never be used to smuggle an operational side channel around MCP or ACP.

No integration may rely on a vendor-specific tool name, Home Assistant entity convention, appliance brand or local network product as a structural dependency of the generic core.

### 5.3 Results

Execution results must cross component boundaries through explicit, versionable contracts. A component must not reach into another component's persistence layer to write or infer state.

## 6. Authorization and capability ownership

Discovery is not authorization.

Agent Control Plane owns operational authorization when it is present in the path. Its administrator-defined MCP capability envelope is authoritative for the execution and must not be broadened by Agent Execution Plane or MCP Capability Bridge.

Provider-native reasoning/information helpers do not broaden that ACP envelope because they are not operational connector capabilities. They remain an Agent Execution Plane/provider-adapter concern and are acceptable only while they cannot access or mutate user infrastructure, AEP private host state or connector secrets outside the governed MCP path.

Agent Execution Plane may perform protocol and provider capability validation, but it must not invent a second semantic authorization system based on labels such as `read`, `write`, `safe`, `dangerous` or vendor descriptions.

MCP Capability Bridge must expose intentionally bounded technical primitives. It must not assume that an upstream Control Plane will make an intrinsically unlimited primitive safe. A default unrestricted operation such as `ssh_exec(command: string)` is therefore not an acceptable substitute for deliberate capability design unless an explicitly scoped product decision later justifies it.

## 7. Secrets and credentials

Secrets belong to the component that must directly use them:

- upstream MCP connector credentials belong to Agent Control Plane when it owns that connector;
- model-provider credentials belong to Agent Execution Plane;
- SSH keys, target HTTP credentials and browser-session credentials belong to MCP Capability Bridge when it owns those target connections.

Secrets must not be copied across components merely for convenience. Contracts must carry opaque authorization material only when the receiving component genuinely needs it to perform its own responsibility.

Provider-native reasoning/information helpers must not be given AEP private credentials, ACP connector secrets or hidden fixed arguments merely to make them more capable. Public-information retrieval must not become a credential or infrastructure side channel.

Each component must independently apply least privilege, redaction and non-disclosure appropriate to the secrets it owns.

## 8. State, retries and failure ownership

Each durable state transition must have one clear owner.

Cross-component designs must avoid two components independently retrying the same logical action without an explicit contract, because this can create duplicate executions or contradictory state.

For Agent Execution Plane, acquisition/result retries belong to the source boundary that owns the relevant lifecycle, while model fallback and MCP-loop safety belong to the execution engine. These responsibilities must remain explicit and non-overlapping.

Failures must remain isolated:

- Agent Execution Plane being unavailable must not prevent Agent Control Plane from serving its independent functions or preserving queued work;
- MCP Capability Bridge being unavailable must make only its capabilities unavailable and must fail closed through consumers that depend on them;
- an installation that does not need the Bridge must not need to install it;
- a standalone Execution Plane must not require Control Plane state.

## 9. Product neutrality and extensibility

The generic core of each component must depend on contracts and capability descriptors, not product names.

Provider- or transport-specific behavior belongs behind adapters with explicit capabilities. Code shaped as growing business-logic branches such as `if home_assistant`, `if gatus`, `if codex`, `if openai`, `if ollama` or appliance-specific equivalents is architectural drift unless it is confined to the adapter that owns that integration.

Provider-native reasoning/information features belong behind the provider adapter that owns them and must not alter the source-defined operational MCP envelope.

Adding a new model provider or concrete source boundary should not require changing unrelated core execution semantics. This extensibility requirement does not justify building unused generic plugin frameworks in advance.

## 10. Independent security boundaries

Every component must be secure when deployed independently within its documented threat model.

Using all three components together may reduce exposed privilege through separation of duties, but no component may delegate its own basic security obligations to another component.

For HAOS packaging, each App must have its own least-privilege runtime, network exposure, persistent-data policy, secret handling and AppArmor profile appropriate to its responsibility.

## 11. Persistence and compatibility

Each component owns its own persistence and schema lifecycle. No component may read or write another component's database directly.

Once a component reaches its production-data preservation cutoff, future schema changes must preserve supported persisted data through explicit, deterministic and tested upgrade paths. Clean reinstall or routine App-data removal is not an acceptable upgrade strategy after that cutoff.

Inter-component contracts must be versionable so that independent upgrade schedules remain possible.

## 12. Delivery and acceptance process

For development work on these projects, a lot is not accepted merely because implementation is complete or Codex reports success.

The normal lifecycle is:

`planned -> implemented -> independently reviewed -> CI conformant -> deployed on HAOS -> real acceptance tested -> accepted`

For every implementation lot:

1. the authoritative plan determines the next bounded scope;
2. the Codex instruction is derived from that plan and states scope, invariants, anti-goals, expected tests and completion criteria;
3. Codex implements the lot without redefining product architecture;
4. the resulting code, diff, tests and CI evidence are independently reviewed;
5. defects or architectural drift are corrected with a focused patch and reviewed again;
6. only conformant code is deployed to HAOS;
7. the real HAOS acceptance recipe is executed;
8. any failure returns to a focused patch/review/deploy/test cycle;
9. only a successful real acceptance updates the plan status to accepted.

This process deliberately separates **implementation evidence** from **production acceptance evidence**.

## 13. Change-placement tests

Before adding a cross-cutting feature, apply these tests:

- If it decides **which work or operational MCP capability is authorized**, it belongs in Agent Control Plane.
- If it decides **how a model reasons, uses permitted provider-native reasoning/information helpers, calls available operational tools and produces a result**, it belongs in Agent Execution Plane.
- If it **turns a non-MCP technical capability into an MCP capability**, it belongs in MCP Capability Bridge.
- If a proposed provider-native helper can access or mutate user infrastructure, local host/private state or connector credentials outside MCP, it is not a reasoning helper and must not bypass the operational MCP boundary.
- If two components would both own the same durable state or retry, the contract is not yet sufficiently defined.
- If a component would become unusable without one of the other two, the design violates the foundational invariant unless the feature is explicitly an optional integration adapter.

## 14. Current sequencing decision

Agent Control Plane and Agent Execution Plane are established as independent applications with a generic MCP boundary between them.

MCP Capability Bridge is the next separately planned application. Its revised project brief, technical design, threat model and implementation plan define a lot-by-lot sequence beginning with the HAOS shell and multi-client MCP namespace boundary. Implementation starts only when explicitly requested and must not reopen the validated ACP/AEP responsibilities.
