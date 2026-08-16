# Agent Execution Plane — Foundational Project Brief

Status: **foundational brief — detailed design not yet started**.

This document defines the product boundary for Agent Execution Plane before implementation planning begins. It intentionally leaves unresolved implementation questions unresolved rather than allowing early code to decide them accidentally.

The root `ARCHITECTURE_CHARTER.md` is normative for this project.

## 1. Product purpose

Agent Execution Plane is a generic model-driven reasoning and execution runtime.

Its job is to accept a bounded unit of work, reason about that work through a configured model/reasoning provider, use only the MCP capabilities available to that execution, and return a result through the active work/result contract.

It is an **execution plane**, not a policy engine and not an infrastructure automation bridge.

A concise product loop is:

`WorkSource -> work unit -> reasoning provider -> MCP tool calls -> result -> WorkSource/result sink`

## 2. Primary goals

Agent Execution Plane should eventually provide:

- a provider-neutral execution core;
- pluggable WorkSource adapters;
- pluggable model/reasoning-provider adapters;
- MCP tool consumption through generic MCP contracts;
- bounded execution lifecycles with clear cancellation, timeout and failure behavior;
- explicit provider capability matching before work begins;
- structured result/report delivery where the active contract requires it;
- observable execution state without becoming a governance/audit system;
- HAOS packaging suitable for always-on local operation;
- independent usefulness without Agent Control Plane or MCP Capability Bridge.

Agent Control Plane is expected to become the first and reference WorkSource integration, but that integration must be an adapter rather than a structural dependency.

## 3. Non-goals

Agent Execution Plane must not:

- own administrator task definitions or immutable task revisions;
- own event intake, mappings, triggers, schedules or grace incidents;
- decide which operational capabilities an identity is authorized to use;
- duplicate Agent Control Plane's identities, leases, reports or governance audit semantics merely for convenience;
- discover broad MCP inventories and silently promote them into authorized tools;
- embed Home Assistant, Gatus, OpenDTU, Cerbo GX, UniFi or any other product as core business logic;
- directly execute SSH, browser automation, arbitrary target HTTP calls or appliance-specific actions as privileged side channels;
- become a replacement for MCP Capability Bridge;
- become a generic workflow/orchestration platform unrelated to model-driven execution;
- require Agent Control Plane in order to run.

## 4. Independence requirement

A standalone Agent Execution Plane must be able to execute work from a non-Control-Plane WorkSource and use compatible MCP servers without installing either of the other suite components.

Conversely, Agent Control Plane must remain useful when Agent Execution Plane is absent.

The Control Plane integration therefore belongs behind a WorkSource/MCP contract, not inside the execution core.

## 5. Conceptual responsibilities

The execution core is expected to coordinate four conceptual boundaries:

1. **WorkSource** — provides a work unit and receives lifecycle/result signals according to its contract.
2. **Reasoning provider** — accepts model context and available tool definitions and produces model output/tool requests.
3. **MCP capability access** — exposes only the MCP tools available to the current execution and carries tool invocations/results.
4. **Result delivery** — returns the final execution outcome through the WorkSource or a dedicated result sink when the contract separates them.

The detailed interface between these boundaries must be designed before implementation.

## 6. WorkSource direction

A WorkSource adapter should isolate external work-management semantics from the execution engine.

Potential responsibilities include some combination of:

- advertising/fetching available work;
- claiming or accepting a work unit;
- providing immutable execution instructions and inputs;
- supplying or referencing the MCP capability surface available to that execution;
- heartbeat/lease maintenance when the source uses leases;
- cancellation observation;
- success/failure/result delivery.

Which of these belong in the generic interface, which are optional capabilities, and which remain source-specific are **open design questions**.

For Agent Control Plane integration, the existing job/lease/report model must be respected rather than reimplemented locally. The adapter must map that external lifecycle into the generic execution lifecycle without changing Control Plane ownership of its durable job state.

## 7. Reasoning-provider direction

Reasoning providers must be adapters behind a common execution-facing contract.

The design should be capable of supporting cloud and local providers, including OpenAI/Codex-compatible services and local Ollama-class runtimes, without hard-coding provider branches into the core loop.

Providers differ materially. The architecture must model declared capabilities rather than pretending all providers are equivalent. Examples that may matter include:

- native tool/function calling;
- structured output support;
- context-window limits;
- streaming behavior;
- model-controlled parallel tool calls;
- multimodal input where relevant;
- cancellation semantics;
- provider-specific usage/accounting metadata.

An execution whose requirements exceed the selected provider's declared capabilities must fail clearly before unsafe or incoherent fallback behavior is attempted.

The exact provider interface, capability vocabulary and first supported providers remain to be designed.

## 8. MCP direction

MCP is the only model-invocable capability path in the generic architecture.

Agent Execution Plane must:

- use only tools actually made available to the current execution;
- preserve exact MCP tool schemas rather than inventing semantic permission from descriptions;
- validate protocol and transport failures into bounded execution errors;
- prevent model output from changing configured MCP endpoints or credentials;
- apply explicit limits to tool-call count, size, duration and result handling once those limits are defined;
- never broaden the capability surface on its own.

When integrated with Agent Control Plane, the Execution Plane should consume the governed MCP surface exposed for that job/identity rather than connecting around the Control Plane to the underlying upstream servers.

When used standalone, its MCP configuration may be provided by another WorkSource or local administrator configuration; the detailed standalone model is still open.

## 9. Authorization boundary

Agent Execution Plane enforces **execution validity**, not operational policy ownership.

It may reject impossible, malformed or provider-incompatible executions. It may enforce local resource bounds. It must not create a parallel semantic authorization layer that overrides or broadens an upstream administrator-defined capability envelope.

If Agent Control Plane is in the path, its authorization decision remains authoritative.

If Agent Execution Plane is used standalone, the administrator is responsible for choosing the MCP servers/capabilities exposed to it through the standalone configuration model that will be designed later.

## 10. Credential ownership

Agent Execution Plane owns credentials it directly needs, especially model/reasoning-provider credentials.

It must not require copies of:

- Agent Control Plane upstream-connector secrets;
- MCP Capability Bridge target SSH keys or target HTTP/browser credentials;
- unrelated infrastructure credentials.

Any WorkSource credential and any MCP client credential required by the Execution Plane belongs to this App only because it directly uses that credential for its own protocol boundary.

Credential storage, rotation, redaction and UI handling must be designed before production use.

## 11. Execution lifecycle

A generic execution will likely need explicit states around concepts such as:

- received/available;
- accepted/claimed;
- preparing;
- reasoning;
- invoking a tool;
- waiting/reasoning again;
- completing;
- succeeded;
- failed;
- cancelled;
- timed out.

These names are illustrative, not yet a committed state machine.

The detailed lifecycle must establish:

- which states are durable locally, if any;
- which state belongs to the WorkSource instead;
- cancellation ownership;
- heartbeat/lease mapping;
- model and tool timeout boundaries;
- crash recovery;
- process restart behavior;
- idempotency and duplicate-execution protection.

No code should invent these semantics before the detailed design is accepted.

## 12. Retry ownership

Retry behavior is a critical design topic and must be explicit.

At minimum, the design must distinguish:

- WorkSource/job-attempt retries;
- provider request retries;
- reasoning-turn retries;
- MCP transport retries;
- individual tool-invocation retries;
- result-delivery retries.

Two layers must not independently repeat the same logical side effect without an idempotency contract. Agent Execution Plane must therefore know which retries it owns and which remain owned by the WorkSource or MCP server.

No generic retry policy should be implemented until this ownership model is decided.

## 13. Persistence direction

Persistence requirements are deliberately undecided at brief stage.

The detailed design must determine whether the App needs durable local state for:

- provider configuration and credentials;
- WorkSource configuration and credentials;
- standalone MCP configuration;
- execution history/diagnostics;
- crash recovery;
- usage accounting;
- administrator settings.

It should not persist copies of Control Plane governance state merely because that state is visible during an execution.

The production-data preservation cutoff must be declared before users are asked to create non-disposable production configuration.

## 14. Observability direction

The App needs enough observability to operate and diagnose execution behavior, but it must not become a duplicate governance/audit database.

Expected areas include:

- current worker health;
- WorkSource connectivity;
- provider connectivity/capability status;
- active execution count and bounded execution summaries;
- normalized failures;
- resource/usage information where providers expose it safely;
- redacted logs.

Exactly what is persisted versus ephemeral remains a design question.

## 15. Security baseline

The detailed plan must include at least:

- least-privilege HAOS runtime and AppArmor policy;
- strict outbound-network and listener design;
- secret non-disclosure and redaction;
- bounded model input/output sizes;
- bounded MCP tool definitions, arguments and results;
- execution deadlines and cancellation;
- protection against model-produced data being interpreted as configuration;
- no shell/browser/HTTP privileged side channel outside MCP;
- fail-closed behavior when required provider, WorkSource or MCP contracts cannot be satisfied.

Prompt injection and untrusted tool output are execution-plane concerns, but the exact mitigations must be designed in the context of the provider/tool loop rather than added as an undefined semantic permission engine.

## 16. Genericity tests

A proposed core feature should be rejected or moved behind an adapter if it requires knowledge such as:

- `if control_plane` inside the reasoning loop;
- `if openai` / `if ollama` outside provider adapters;
- `if home_assistant` / `if gatus` / appliance-specific behavior;
- direct interpretation of a particular MCP server's tool names;
- direct SSH/HTTP/browser target execution.

The core should understand contracts, execution requirements and declared capabilities — not products.

## 17. Initial integration target

The first full integration target is expected to be:

`Agent Control Plane job -> Agent Execution Plane -> reasoning provider -> governed MCP tools exposed through Agent Control Plane -> result/report back to Agent Control Plane`

This is the **reference scenario**, not the product definition.

A standalone scenario must remain architecturally possible:

`other WorkSource/manual/API -> Agent Execution Plane -> reasoning provider -> configured MCP server(s) -> result`

## 18. Detailed-design questions to resolve next

Before substantial implementation begins, the detailed design must explicitly settle at least:

1. the generic WorkSource interface and optional capabilities;
2. the exact mapping to Agent Control Plane's existing job/lease/report protocol;
3. the reasoning-provider interface and capability model;
4. the model/tool conversation loop and termination rules;
5. MCP session ownership and per-execution capability exposure;
6. timeouts, cancellation and retry ownership at every layer;
7. concurrency and worker scheduling;
8. crash/restart and idempotency semantics;
9. local persistence requirements and production-data cutoff;
10. provider and WorkSource credential management;
11. standalone operation and administration UX;
12. HAOS listener/network/AppArmor boundaries;
13. observability and redaction;
14. initial provider and WorkSource scope for the first accepted release;
15. CI and real-HAOS acceptance gates.

These questions are the next design work. Codex should not be asked to choose their answers implicitly through implementation.

## 19. Delivery discipline

Agent Execution Plane will follow the suite delivery lifecycle defined in `ARCHITECTURE_CHARTER.md`.

The authoritative implementation plan will be created only after the detailed architecture is agreed. Each Codex lot will then be bounded by that plan and will require independent code/diff/test/CI review plus real HAOS acceptance before being marked accepted.
