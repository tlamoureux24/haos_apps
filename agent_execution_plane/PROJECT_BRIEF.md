# Agent Execution Plane — Foundational Project Brief

Status: **foundational brief — detailed design not yet started**.

This document defines the strict product boundary for Agent Execution Plane before implementation planning begins.

The root `ARCHITECTURE_CHARTER.md` remains normative. Where this brief is more specific, Agent Execution Plane must follow the narrower responsibility defined here.

## 1. Product purpose

Agent Execution Plane is a **model execution engine**.

Its entire product responsibility is:

1. receive a job from a source;
2. give the model exactly the job content and MCP tools supplied for that execution;
3. run the model/tool-calling loop required to execute that job;
4. receive the model's result;
5. return that result to the configured destination.

A concise product flow is:

`job source -> Agent Execution Plane -> model + supplied MCP tools -> model result -> result destination`

Agent Execution Plane is not a control plane, policy engine, workflow engine, job designer or infrastructure bridge.

## 2. Reference integration with Agent Control Plane

The first and reference integration is deliberately simple:

`Agent Control Plane -> Agent Execution Plane -> reasoning model -> governed MCP tools -> model result -> Agent Control Plane`

Agent Control Plane already owns the job, its instructions/input, the capability envelope, its lifecycle and the report contract. Agent Execution Plane must consume that existing contract with the minimum adaptation necessary to call the selected reasoning provider and MCP interface.

For this integration:

- Agent Control Plane decides which job is to be executed;
- Agent Control Plane supplies the content that is to be given to the model;
- Agent Control Plane supplies/exposes the MCP tools available to that execution;
- Agent Execution Plane does not add semantic instructions, business context, capabilities or policy;
- Agent Execution Plane executes the job through the selected model;
- Agent Execution Plane returns the model-produced result to Agent Control Plane;
- factual technical failures that prevent execution are reported back to Agent Control Plane rather than turned into policy decisions by Agent Execution Plane.

The existing Agent Control Plane job/MCP/report behavior already exercised successfully with Codex is the reference behavior. Agent Execution Plane must not redesign that contract merely to introduce additional abstraction.

## 3. Strict execution-only rule

Agent Execution Plane **executes and reports; it does not decide**.

It must not decide:

- what job should exist;
- which job should run next as a matter of business policy;
- what the job objective should be;
- what additional context the model should receive;
- which operational capabilities should be authorized;
- whether missing capabilities should be granted;
- whether a model conclusion is correct or sufficient as a business result;
- whether the job should be retried, re-created, escalated or otherwise continued;
- what another component should do with the returned result.

If the model concludes that the supplied tools or information are insufficient, that conclusion is part of the **model result** and is returned to the destination. Agent Execution Plane must not reinterpret that conclusion into its own business-policy state machine.

If Agent Execution Plane itself encounters a technical problem — for example a provider transport failure or an MCP protocol failure that prevents the requested execution from continuing — it reports the factual technical failure to the destination. It does not decide the subsequent policy response.

## 4. No semantic enrichment

Everything Agent Execution Plane presents to the model for a job must originate from the job source or from the MCP capability surface supplied for that execution.

Agent Execution Plane must not silently add:

- new job instructions;
- additional business context;
- inferred objectives;
- source-specific metadata as reasoning context;
- extra MCP tools;
- semantic authorization labels;
- policy prompts that alter the meaning of the supplied job.

Provider-specific formatting required to transmit the supplied content is an implementation detail and is allowed, but it must not change or enrich the semantic content of the job.

Likewise, internal runtime information such as process IDs, local session identifiers, health state or diagnostics must not become model context unless the job source explicitly supplied that information as part of the job.

## 5. MCP tool rule

MCP is the only model-invocable capability path in Agent Execution Plane.

The engine uses only the MCP tools supplied or exposed for the current execution. It must not discover and add unrelated capabilities on its own, connect around a governing source to hidden upstream servers, or create direct infrastructure side channels.

When Agent Control Plane is used, Agent Execution Plane consumes only the governed MCP capability surface made available by Agent Control Plane for the execution.

The capability surface must never be broadened by Agent Execution Plane during execution.

If the model needs a capability that is not available, Agent Execution Plane does not obtain one. The model may report that limitation in its result, which is then returned to the destination.

## 6. Reasoning-provider responsibility

Agent Execution Plane owns the technical integration with reasoning/model providers because invoking the model is its core job.

The engine should support provider adapters so that different compatible cloud or local reasoning providers can be used without embedding provider-specific branches throughout the execution loop.

Expected provider families may include OpenAI/Codex-compatible providers, other cloud providers and local runtimes such as Ollama, subject to later detailed design and actual provider capabilities.

Agent Execution Plane may perform only the technical work necessary to use the configured provider, including protocol formatting, tool-call exchange, structured-output transport where supported, cancellation/timeout handling required by the provider, and normalization of technical provider failures.

It must not compensate for a provider by inventing new job semantics or policy.

Model-provider credentials belong to Agent Execution Plane because it directly uses them.

## 7. Model/tool execution loop

The core runtime should remain conceptually small:

1. receive the job and supplied capability surface;
2. call the selected reasoning provider with the supplied job content and tool definitions;
3. when the model requests an allowed MCP tool, invoke that tool;
4. return the MCP result to the model;
5. continue until the model returns its final result or the execution is technically unable to continue;
6. return the model result, or the factual technical failure, to the destination.

The detailed protocol mechanics, bounds and timeout values remain to be designed, but they must serve this loop rather than create a second orchestration product around it.

## 8. Standalone independence

Agent Execution Plane must remain fully usable without Agent Control Plane.

Independence does **not** mean that Agent Execution Plane creates its own jobs, authorization policy or orchestration system. It means another system can supply a job and receive its result.

Standalone operation will therefore expose a small, documented generic API acting as the source/destination boundary.

Conceptually:

`external caller -> documented Execution Plane API -> model + supplied MCP tools -> result -> external caller`

That API must allow an external caller to provide the information required for execution and receive the resulting model output or factual technical execution failure.

The standalone API must remain deliberately small. It must not grow into a parallel task database, scheduler, trigger engine, identity/governance system or workflow platform.

The exact API schema, authentication and MCP connection representation will be decided during detailed design.

## 9. Independence from MCP Capability Bridge

MCP Capability Bridge is optional.

If used, it is simply an MCP server whose tools may be supplied to an Agent Execution Plane execution, directly in standalone usage or through Agent Control Plane.

Agent Execution Plane must not know how Bridge capabilities are implemented internally and must not implement SSH, target HTTP, browser automation or appliance-specific execution itself.

## 10. Non-goals

Agent Execution Plane must not:

- own Agent Control Plane task definitions or task revisions;
- own Agent Control Plane event intake, mappings, triggers, schedules or grace incidents;
- own operational authorization policy;
- choose which MCP tools a governed job is permitted to use;
- duplicate Agent Control Plane's job governance, reports, audit or policy logic;
- become a generic WorkSource framework;
- create a generic workflow/orchestration engine;
- classify model conclusions into business outcomes;
- decide job retry/escalation policy;
- add business context or instructions that were not supplied by the job source;
- discover extra tools for a running job;
- directly execute SSH, browser automation, arbitrary target HTTP calls or appliance-specific actions outside MCP;
- embed Home Assistant, Gatus, OpenDTU, Cerbo GX, UniFi or any other product as core business logic;
- require Agent Control Plane or MCP Capability Bridge in order to run.

## 11. State and persistence direction

Agent Execution Plane should retain only state genuinely required to operate the engine itself.

Likely persistent configuration includes model-provider configuration/credentials and application settings. Additional persistence must be justified by an actual execution-engine requirement during detailed design.

Agent Execution Plane must not persist a shadow copy of Agent Control Plane governance state merely because a job passes through it.

It must not introduce a durable job-management subsystem unless a later concrete technical requirement proves one necessary; standalone callers remain the owners of the jobs they submit.

The production-data preservation cutoff will be declared before users are asked to create non-disposable production configuration.

## 12. Observability

Operational visibility should remain limited to what is necessary to run and diagnose the execution engine, for example:

- engine health;
- configured provider health;
- current technical execution activity;
- bounded/redacted technical errors;
- provider usage information where safely available.

Observability must not become a second governance/audit system and must not reinterpret model results.

## 13. Security baseline

Detailed design must include the security necessary to run the engine safely without changing its responsibility:

- least-privilege HAOS runtime and AppArmor policy;
- protected model-provider credentials;
- authenticated standalone API;
- strict input/output and transport bounds;
- bounded MCP definitions, arguments and results;
- execution/provider/MCP timeouts required to prevent stuck execution;
- secret redaction and non-disclosure;
- no privileged shell/browser/target-HTTP side channel outside MCP;
- no model-produced data interpreted as configuration or new authorization;
- no capability broadening by Agent Execution Plane.

Security mechanisms must constrain the execution engine technically; they must not turn it into a business-policy engine.

## 14. Genericity test

A proposed Agent Execution Plane feature belongs in the product only if it is required to:

> receive a supplied job, have a configured model execute it with the supplied MCP tools, and return the resulting model output.

If a feature instead decides what work should exist, what capabilities should be authorized, what a model conclusion means operationally, or what should happen after the result is returned, it belongs elsewhere.

Provider-specific mechanics belong behind provider adapters. Source/destination-specific transport mechanics belong at the thin source/destination boundary. Product/vendor-specific infrastructure mechanics belong behind MCP, not in Agent Execution Plane.

## 15. Initial design questions

Before implementation begins, detailed design now needs to settle only the mechanics necessary for this deliberately small product:

1. the exact Agent Control Plane integration using its existing job/MCP/report contracts;
2. the minimal standalone source/destination API contract;
3. the reasoning-provider adapter interface and first provider scope;
4. the exact model/tool-calling loop;
5. how supplied MCP tools are represented and invoked in both Control Plane and standalone modes;
6. technical timeout/cancellation/error propagation required to keep an execution bounded;
7. minimal concurrency behavior required to run more than one execution safely, if included in the first release;
8. provider credential/configuration handling;
9. the minimum local persistence actually required;
10. HAOS network/listener/AppArmor boundaries;
11. bounded observability and redaction;
12. CI and real-HAOS acceptance gates.

These questions must be answered without expanding the product beyond its execution-only responsibility.

## 16. Delivery discipline

The authoritative implementation plan will be created only after the detailed design is agreed.

For every future implementation lot:

`planned -> implemented by Codex -> independently reviewed -> CI validated -> deployed on HAOS -> real acceptance tested -> accepted`

A Codex summary alone never marks a lot complete. Any defect found during review or HAOS acceptance is patched, reviewed and retested before the lot is recorded as accepted.
