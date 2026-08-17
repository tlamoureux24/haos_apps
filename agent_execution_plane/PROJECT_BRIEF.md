# Agent Execution Plane — Foundational Project Brief

Status: **foundational brief — detailed design in progress, no implementation started**.

This document defines the strict product boundary and the operational decisions already validated for Agent Execution Plane before implementation planning begins.

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

Agent Execution Plane is not a control plane, scheduler, policy engine, workflow engine, job designer or infrastructure bridge.

## 2. Reference integration with Agent Control Plane

The first and reference integration is deliberately simple:

`Agent Control Plane -> Agent Execution Plane -> reasoning model -> governed MCP tools -> model result -> Agent Control Plane`

Agent Control Plane already owns the job, its instructions/input, the capability envelope, its lifecycle and the report contract. Agent Execution Plane consumes that existing contract with the minimum adaptation necessary to run the selected local execution profile and MCP loop.

For this integration:

- Agent Control Plane decides which jobs exist and when they become available;
- Agent Control Plane supplies the job content that is to be given to the model;
- Agent Control Plane supplies/exposes the MCP tools available to that execution;
- Agent Control Plane remains model-neutral and does not choose the reasoning provider used by Agent Execution Plane;
- Agent Execution Plane does not add semantic instructions, business context, capabilities or policy;
- Agent Execution Plane executes the job through its own configured model profiles;
- Agent Execution Plane returns the model-produced result to Agent Control Plane;
- factual technical failures that prevent execution are reported back to Agent Control Plane rather than turned into policy decisions by Agent Execution Plane.

The existing Agent Control Plane job/MCP/report behavior already exercised successfully with Codex is the reference behavior. Agent Execution Plane must not redesign that contract merely to introduce additional abstraction.

## 3. Strict execution-only rule

Agent Execution Plane **executes and reports; it does not decide business policy**.

It must not decide:

- what job should exist;
- when a task becomes a job;
- what the job objective should be;
- what additional business context the model should receive;
- which operational capabilities should be authorized;
- whether missing capabilities should be granted;
- whether a model conclusion is correct or sufficient as a business result;
- whether the source should retry, recreate, escalate or otherwise continue the job;
- what another component should do with the returned result.

If the model concludes that the supplied tools or information are insufficient, that conclusion is part of the **model result** and is returned unchanged in meaning to the destination. Agent Execution Plane must not reinterpret that conclusion into its own business-policy state machine.

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

Internal runtime information such as process IDs, local session identifiers, health state or diagnostics must not become model context unless the job source explicitly supplied that information as part of the job.

## 5. MCP tool rule

MCP is the only model-invocable capability path in Agent Execution Plane.

The engine uses only the MCP tools supplied or exposed for the current execution. It must not discover and add unrelated capabilities on its own, connect around a governing source to hidden upstream servers, or create direct infrastructure side channels.

When Agent Control Plane is used, Agent Execution Plane consumes only the governed MCP capability surface made available by Agent Control Plane for the execution.

The capability surface must never be broadened by Agent Execution Plane during execution.

If the model needs a capability that is not available, Agent Execution Plane does not obtain one. The model may report that limitation in its result, which is then returned to the destination.

A reasoning model does not need to speak MCP itself; Agent Execution Plane handles MCP. The model/provider must, however, support the tool/function-calling behavior required to use the supplied MCP tools.

## 6. Model profiles and administrator priority

Agent Execution Plane owns its reasoning/model-provider configuration because invoking a model is its core technical responsibility.

The first release supports two provider adapter families: **Ollama-compatible** endpoints and **OpenAI-compatible** endpoints. Multiple model profiles may be configured across either family, including local and remote endpoints.

Each model profile has at least these administrator-controlled properties:

- enabled/disabled state;
- explicit priority/order in the model list;
- provider/model technical configuration and credentials;
- a timeout covering the model's entire attempt on one job.

The rules are:

- model priority belongs to Agent Execution Plane, not Agent Control Plane;
- disabled means only that the administrator does not currently want the model used for jobs;
- disabled does not mean invalid, broken or untested;
- every new job starts again from the top of the administrator-defined priority list;
- disabled profiles are skipped;
- Agent Execution Plane never automatically reorders models, changes their priority or disables them because of a temporary failure;
- a model that failed on a previous job is retried normally according to its configured priority on the next job.

Provider-specific mechanics belong behind provider adapters. The execution loop must not contain growing `if openai`, `if ollama`, or equivalent product branches outside those adapters.

Model-provider credentials belong to Agent Execution Plane because it directly uses them.

## 7. Model configuration lifecycle

A model profile may be stored only when its configuration has passed the required technical validation.

For a new profile:

- the initial technical test must succeed before the profile can be created;
- this requirement applies whether the new profile is initially enabled or disabled.

For an existing profile:

- a candidate configuration is tested before replacing the current one;
- if the candidate test fails, the previous valid configuration remains fully in place;
- the UI must state clearly that the new configuration could not be applied and that the previous configuration was preserved;
- useful bounded technical failure information should be shown without exposing secrets.

While a model profile is executing the active job:

- it cannot be disabled;
- it cannot be deleted;
- its technical configuration cannot be modified in a way that could affect the running attempt;
- the UI must state clearly that the model is currently in use;
- its position in the priority list **may still be changed**, because reordering affects only future jobs and does not modify the active execution.

A model that is not currently in use may be deleted whether enabled or disabled.

## 8. Model compatibility and health

A model/provider profile that cannot support the tool/function-calling required by Agent Execution Plane is incompatible and must never receive a job.

For a new profile, known incompatibility prevents creation. For an existing profile that later becomes incompatible, the UI must show an explicit `Incompatible` state and the profile is excluded from execution until corrected or removed by the administrator.

At application startup, Agent Execution Plane tests all configured model profiles, enabled and disabled, to establish their current technical state. A failed availability test must not prevent the App itself from starting and must not change the administrator's enabled/disabled choice or priority order.

Periodic automatic health checks are allowed only when they can be guaranteed not to consume billable/provider usage such as model inference tokens, credits or quota. No automatic health check may submit a prompt or trigger model inference.

If a provider has no guaranteed non-billable health mechanism, Agent Execution Plane must not perform periodic automatic checks against that provider. Its UI may show an unverified/unknown current state until a legitimate test or real use supplies newer information.

Health state is informative. An enabled priority-1 model that previously appeared unavailable is still tried first on the next job, according to the administrator's order.

## 9. Single-job worker behavior

Version one has exactly **one execution slot**.

Agent Execution Plane never executes two jobs concurrently and never claims a second job while the current job or its result-delivery phase is still active.

When integrated with Agent Control Plane:

- when the execution slot is free and at least one enabled compatible model exists, Agent Execution Plane polls for work every **1 second**;
- polling remains a fixed 1-second mechanism even while Agent Control Plane is temporarily unreachable;
- when a job is obtained, polling for new jobs stops;
- after the current job has fully completed and its result has been accepted by the destination, polling resumes immediately;
- if no model profile is enabled, Agent Execution Plane does not claim jobs and the UI clearly reports that execution is waiting for an enabled model.

This worker loop is not a scheduler. Agent Control Plane remains responsible for deciding when tasks become jobs.

## 10. Model selection and fallback

For every new job, Agent Execution Plane evaluates enabled compatible model profiles from highest to lowest administrator-defined priority.

If a model suffers a technical failure **before any MCP tool action has been executed for that job**, Agent Execution Plane may continue to the next enabled compatible model in the list.

The fallback model receives:

- the original job content;
- the original supplied MCP capability surface;
- no reasoning state, conversation, summary or other semantic material from the failed model.

The fallback model starts from zero and receives its own complete configured timeout.

Once any MCP tool action has actually been executed for the job, Agent Execution Plane must not automatically switch to another model for that job. A later technical failure is reported to the destination instead of replaying the job through another model and risking duplicate effects.

If every enabled compatible model fails technically before any MCP action occurs, Agent Execution Plane stops the attempt and reports the factual technical failure to the destination. It does not keep the job for an autonomous retry later.

## 11. Per-model timeout

Each model profile has its own configurable timeout. A newly created model profile uses **5 minutes by default** unless the administrator chooses another value.

The timeout covers that model's **entire attempt on the job**, from the start of the attempt until the model returns its final result or the attempt cannot continue. It does not reset at each reasoning turn or MCP exchange.

If a model times out before any MCP action has been executed, the next enabled compatible model may be tried according to the priority/fallback rule.

If the timeout occurs after an MCP action has been executed, no automatic model fallback is allowed and the technical timeout is reported to the destination.

## 12. Agent Control Plane lease/connectivity behavior

When a job has been claimed from Agent Control Plane, Execution Plane must respect the validity of the existing Control Plane lease rather than invent a separate execution-ownership system.

A single transient communication/heartbeat failure does not immediately stop a running job. Agent Execution Plane may continue while the already-issued lease remains unquestionably valid and it attempts to restore communication.

As soon as lease validity can no longer be guaranteed:

- Agent Execution Plane stops continuing the reasoning attempt;
- no new MCP tool invocation may be issued for that job;
- the interruption is reported factually to Agent Control Plane when communication permits.

The current Agent Control Plane behavior does not allow an already-claimed job to be manually cancelled, so Agent Execution Plane must not invent a separate claimed-job cancellation protocol for the reference integration.

## 13. Result delivery and blocking behavior

Agent Execution Plane handles only one current execution/result at a time.

When the model has produced its final result, Agent Execution Plane persists the result until the configured destination has explicitly accepted or acknowledged it.

While a result is awaiting delivery/acknowledgement:

- no new job is accepted or claimed;
- the model is not run again;
- the same persisted result is retained;
- the UI clearly shows that a result is awaiting delivery and the known technical reason when delivery is failing.

For Agent Control Plane integration, result delivery is retried every **1 second** until Control Plane accepts it. Once accepted, the temporary local result is deleted and polling for the next job resumes immediately.

The administration UI must provide an explicit, confirmed **abandon/delete pending result** action as an exceptional recovery mechanism. This allows the administrator to unblock the engine if a result can no longer be delivered. The action removes the local pending result and does not rerun the model or decide what the source should do with the original job.

## 14. Crash/restart safety and minimal persistence

Agent Execution Plane persists only what is necessary to avoid losing the state needed to finish or truthfully report its current execution responsibility.

Durable state includes:

- model/provider configuration and credentials;
- application settings;
- the minimum reference required to identify a job/execution that was active if the process restarts before a final result exists;
- a final result that exists but has not yet been accepted/acknowledged, plus the minimum information necessary to deliver it.

It must not keep a permanent shadow copy of Agent Control Plane jobs, model conversations or reasoning history.

If Agent Execution Plane restarts while a final result is waiting for delivery, it restores that exact pending result, remains blocked from new work and continues delivery attempts without rerunning the model.

If Agent Execution Plane restarts while a job was still being executed and no final result existed, it **must not automatically rerun the job**. MCP actions may already have occurred. Instead it records/reports the factual interruption to the source when possible and waits for the source to determine the next policy action.

## 15. Standalone independence and API

Agent Execution Plane must remain fully usable without Agent Control Plane.

Independence does **not** mean that Agent Execution Plane creates its own tasks, scheduler, authorization policy or job orchestration system. It means another system can submit one execution and receive its result through a small documented API.

The standalone API is asynchronous and deliberately minimal.

Conceptually:

- `POST /execute` submits one execution and returns an opaque execution identifier;
- `GET /executions/<id>` retrieves the current execution state and, when available, the final result;
- `POST /executions/<id>/ack` explicitly confirms that the caller has successfully received the final result.

If the engine is already executing a request or holding a final result that has not yet been acknowledged, a new `POST /execute` is refused immediately with a clear busy response. There is no standalone internal queue.

A standalone final result is persisted and the engine remains blocked until the caller sends the explicit acknowledgement. Merely calling `GET /executions/<id>` does not release the result.

The API and logs should distinguish at least:

- execution accepted;
- result available;
- result consulted/retrieved through `GET`;
- result acknowledged through `ack`;
- pending result manually abandoned by the administrator.

The administration UI exposes the same explicit, confirmed pending-result abandonment action in standalone mode.

The standalone API documentation must describe this submit/retrieve/acknowledge lifecycle clearly so external callers know that failing to acknowledge a result intentionally keeps the single execution slot occupied.

Standalone API access uses an **opaque Bearer token** managed by Agent Execution Plane. The token is generated by the application, displayed to the administrator only once when issued, and is never recoverable later in clear text. The administration UI must allow that standalone API credential to be revoked and replaced. Authentication follows the same simple credential philosophy already used by Agent Control Plane rather than introducing a separate login/session system.

The exact standalone request/response payload schemas remain to be designed.

## 16. Independence from MCP Capability Bridge

MCP Capability Bridge is optional.

If used, it is simply an MCP server whose tools may be supplied to an Agent Execution Plane execution, directly in standalone usage or through Agent Control Plane.

Agent Execution Plane must not know how Bridge capabilities are implemented internally and must not implement SSH, target HTTP, browser automation or appliance-specific execution itself.

## 17. Non-goals

Agent Execution Plane must not:

- own Agent Control Plane task definitions or task revisions;
- own Agent Control Plane event intake, mappings, triggers, schedules or grace incidents;
- own operational authorization policy;
- choose which MCP tools a governed job is permitted to use;
- duplicate Agent Control Plane's job governance, reports, audit or policy logic;
- create a generic WorkSource framework;
- create a generic workflow/orchestration engine;
- create its own scheduler;
- maintain an internal queue of waiting jobs in version one;
- classify model conclusions into business outcomes;
- decide source-level retry/escalation policy;
- add business context or instructions that were not supplied by the job source;
- discover extra tools for a running job;
- directly execute SSH, browser automation, arbitrary target HTTP calls or appliance-specific actions outside MCP;
- embed Home Assistant, Gatus, OpenDTU, Cerbo GX, UniFi or any other product as core business logic;
- require Agent Control Plane or MCP Capability Bridge in order to run.

## 18. Observability

Operational visibility should remain limited to what is necessary to run and diagnose the execution engine, including:

- engine health;
- source/destination connectivity relevant to the current execution;
- configured model state, priority, enabled/disabled state and compatibility;
- current technical execution activity;
- pending-result delivery state;
- bounded/redacted technical errors;
- provider usage information where safely available.

Observability must not become a second governance/audit system and must not reinterpret model results.

## 19. Security baseline

Detailed design must include the security necessary to run the engine safely without changing its responsibility:

- least-privilege HAOS runtime and AppArmor policy;
- protected model-provider credentials;
- authenticated standalone API;
- strict input/output and transport bounds;
- bounded MCP definitions, arguments and results;
- model/MCP timeouts required to prevent stuck execution;
- secret redaction and non-disclosure;
- no privileged shell/browser/target-HTTP side channel outside MCP;
- no model-produced data interpreted as configuration or new authorization;
- no capability broadening by Agent Execution Plane;
- crash/restart handling that never blindly replays a possibly side-effecting job.

Security mechanisms must constrain the execution engine technically; they must not turn it into a business-policy engine.

## 20. Genericity test

A proposed Agent Execution Plane feature belongs in the product only if it is required to:

> receive a supplied job, have one of the administrator-configured models execute it with the supplied MCP tools, and return the resulting model output.

If a feature instead decides what work should exist, what capabilities should be authorized, what a model conclusion means operationally, or what the source should do after the result is returned, it belongs elsewhere.

Provider-specific mechanics belong behind provider adapters. Source/destination-specific transport mechanics belong at the thin source/destination boundary. Product/vendor-specific infrastructure mechanics belong behind MCP, not in Agent Execution Plane.

## 21. Remaining detailed-design questions

Before implementation begins, remaining work should stay concrete and limited to mechanics necessary for this deliberately small product, including:

1. the exact Agent Control Plane integration endpoints/credentials using its existing job/MCP/report contracts;
2. exact standalone API payload schemas;
3. the provider-adapter interface for the validated Ollama-compatible and OpenAI-compatible provider families;
4. exact technical definitions used to distinguish pre-MCP provider failure from post-MCP failure;
5. the exact MCP client/session mechanics for the supplied capability surface;
6. model-profile UI fields and provider-specific configuration fields;
7. the allowed configurable timeout range around the validated **5-minute default**;
8. exact persistence schema for active-interruption and pending-result recovery;
9. HAOS listener/network/AppArmor boundaries;
10. bounded logs, redaction and UI state presentation;
11. CI tests and real-HAOS acceptance gates.

These questions must be answered without expanding the product beyond its execution-only responsibility.

## 22. Delivery discipline

The authoritative implementation plan will be created only after the detailed design is agreed.

For every future implementation lot:

`planned -> implemented by Codex -> independently reviewed -> CI validated -> deployed on HAOS -> real acceptance tested -> accepted`

A Codex summary alone never marks a lot complete. Any defect found during review or HAOS acceptance is patched, reviewed and retested before the lot is recorded as accepted.