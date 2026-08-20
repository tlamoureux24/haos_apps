# Agent Execution Plane — Foundational Project Brief

Status: **foundational product boundary — Lots 0 and 1 accepted; remaining implementation follows this brief**.

This document defines the strict product boundary and validated behavior of Agent Execution Plane throughout implementation.

The root `ARCHITECTURE_CHARTER.md` remains normative. Where this brief is more specific, Agent Execution Plane follows the narrower responsibility defined here.

## 1. Product purpose

Agent Execution Plane is a **model execution engine**.

Its responsibility is deliberately small:

1. receive one execution from a source;
2. give a configured reasoning model exactly the source-provided objective/input and exactly the model-invocable MCP capability envelope supplied by that source;
3. run the model/tool-calling loop;
4. obtain the final model result or a factual technical failure;
5. return that outcome to the source/destination.

Conceptually:

`source -> Agent Execution Plane -> model + source-supplied MCP capability envelope -> result -> source`

Agent Execution Plane is not a control plane, scheduler, workflow engine, policy engine, job designer or infrastructure bridge.

The source decides what work and capability envelope exist. Agent Execution Plane executes that already-defined contract; it does not derive, select, authorize, broaden or semantically narrow the capability envelope itself.

## 2. One execution contract, regardless of source

**Agent Control Plane integration and standalone API usage use the same execution engine and the same functional contract.**

There are not two different execution behaviors to design.

In both cases, the source supplies the execution material:

- objective/instruction;
- input data;
- MCP endpoint/access information needed for that execution;
- the exact model-invocable MCP capability envelope already selected/authorized by the source;
- an output/result schema when the source requires structured output.

That capability envelope is an **input contract**, not an Agent Execution Plane authorization decision. Execution Plane may perform only the protocol/schema consistency checks needed to execute the supplied envelope safely. It must not replace it with a different subset, add capabilities from MCP discovery, classify tools semantically, or reconstruct source policy.

Agent Execution Plane then applies its configured model priority deterministically, runs exactly the same model/MCP loop and produces exactly one result or factual technical failure.

The only differences between Agent Control Plane mode and standalone usage are **transport and lifecycle mechanics at the boundary**:

- Agent Control Plane exposes jobs, leases, governed MCP capabilities and result completion through its existing MCP surface;
- the standalone API accepts the equivalent execution material directly and exposes explicit result retrieval/acknowledgement.

Those boundary differences must never create divergent execution semantics. The standalone API documentation must describe clearly how to submit the same execution material that Agent Control Plane supplies through its existing contract.

## 3. Reference Agent Control Plane integration

Reference flow:

`Agent Control Plane -> Agent Execution Plane -> reasoning model -> governed virtual MCP capabilities -> model result -> Agent Control Plane`

Agent Control Plane owns the task/job, its business lifecycle, instructions/input, authorization, capability envelope, retry policy and report contract.

Agent Control Plane also owns:

- upstream MCP connector configuration, endpoints and credentials;
- connector discovery and inventories;
- administrator task/tool selection;
- namespacing/virtualization of selected capabilities;
- effective schemas and restrictions such as `fixed_arguments_v1`;
- per-invocation authorization and fail-closed revalidation before any upstream call.

`jobs_claim_v1` returns the claimed job with its `allowed_capabilities`. That field is the **authoritative model-invocable capability envelope** for the execution. Agent Execution Plane must not derive a different capability set from the ACP MCP server's complete `tools/list` result.

The ACP public MCP surface intentionally contains two different categories of tools:

1. **source-boundary lifecycle tools** used by Agent Execution Plane itself, such as claim, heartbeat, complete and fail;
2. **virtual task capabilities** governed by ACP and eligible for model exposure only when they are present in the claimed job's `allowed_capabilities` envelope.

The lifecycle tools remain boundary mechanics and are never model-invocable merely because they appear in `tools/list`.

Agent Execution Plane:

- does not create or choose ACP jobs;
- does not add semantic instructions or business context;
- does not authorize, select or broaden capabilities;
- does not inspect ACP connector configuration or upstream credentials;
- does not reconstruct connector provenance, hidden fixed arguments or ACP restrictions;
- uses ACP lifecycle tools only in its ACP source boundary, never as model tools;
- maps the claimed job's `allowed_capabilities` into the common execution contract exactly;
- may verify mechanically that each claimed capability still exists on the same ACP MCP session with the expected effective input schema;
- executes the claimed job through its configured models;
- returns the model-produced result or factual technical execution failure;
- does not choose what ACP should do with that result.

The reference transport is ACP's existing authenticated **Streamable HTTP MCP surface**. Execution Plane is configured with:

- the ACP MCP endpoint;
- the opaque Bearer credential of a worker identity authorized by ACP to claim, heartbeat, complete and fail jobs.

The same governed MCP surface exposes lifecycle tools to the AEP boundary and the virtual capabilities of the active job. No ACP-specific parallel execution API and no duplicated lease or authorization protocol are introduced.

## 4. Strict execution-only rule

Agent Execution Plane **executes and reports; it does not decide business or authorization policy**.

It must not decide:

- what work should exist;
- when a task becomes a job;
- what objective or business context should be added;
- which operational capabilities should be authorized;
- which capabilities from a broader server inventory should become model-visible;
- whether missing capabilities should be granted;
- whether the model's conclusion is business-correct or sufficient;
- whether the source should retry, recreate, escalate or continue work;
- what another component should do after receiving the result.

The source-supplied capability envelope is authoritative. AEP may reject an execution when that contract cannot be executed consistently or safely at the protocol level, but that rejection is a factual technical failure, not a new authorization decision.

If the model concludes that tools or information are insufficient, that is a **model result**, not an Execution Plane technical failure.

If Execution Plane itself encounters a provider, MCP, transport or runtime problem that prevents execution, it reports the factual technical failure without inventing the subsequent policy response.

## 5. No semantic enrichment

Everything presented to the model for an execution originates from the source or from the source-governed MCP capability metadata corresponding to the supplied capability envelope.

Execution Plane must not silently add:

- new job instructions;
- inferred objectives;
- business context;
- hidden tools;
- source-boundary lifecycle tools;
- semantic authorization labels;
- policy prompts that change the meaning of the source request.

Provider-specific formatting necessary to transmit the same content is allowed, but it must not alter its meaning.

## 6. MCP capability rule

MCP is the only model-invocable capability path in Agent Execution Plane.

Every execution carries an exact model-invocable capability envelope supplied by its source. Execution Plane uses `tools/list` only as a **technical consistency mechanism** for that envelope: it may confirm that the named capabilities exist and that their effective input schemas still match what the source supplied. `tools/list` is never an authorization source for AEP.

Therefore:

- AEP does not discover tools and then decide which ones are allowed;
- AEP does not add a tool merely because it appears in MCP discovery;
- AEP does not expose source-boundary lifecycle tools to the model unless the source contract itself explicitly made them model capabilities;
- an empty source capability envelope means zero model-visible tools even if the MCP server exposes other tools;
- a capability missing from the MCP server or presenting a mismatched effective schema makes the supplied execution contract technically inconsistent and fails closed;
- a model request for a tool outside the frozen source envelope is rejected locally without dispatch;
- local JSON-schema argument validation enforces the already-supplied technical contract and is not a second semantic authorization system.

For ACP specifically, the `allowed_capabilities` from the claimed job provide the authoritative names and effective schemas. ACP remains responsible for connector selection, virtual naming, argument restrictions, hidden/fixed argument injection, authorization and upstream dispatch. AEP neither knows nor recreates those decisions.

A reasoning model does not need to speak MCP itself. Execution Plane speaks MCP and maps the source-supplied capabilities into the provider's supported tool/function-calling mechanism.

A model/provider that cannot support the required tool/function-calling behavior is incompatible and must not receive work.

## 7. Model provider scope

The first release supports three provider adapter families:

- **Ollama-compatible** endpoints;
- generic **OpenAI-compatible** endpoints with configurable base URL and optional Bearer/API credential;
- official **OpenAI ChatGPT OAuth** through the pinned Codex app-server runtime and a ChatGPT subscription.

Multiple models may be configured across these families, including local and remote generic endpoints. `openai_chatgpt_oauth` never accepts an OpenAI Platform API key and never falls back implicitly to API billing. Its shared ChatGPT account login is owned and persisted by the official Codex runtime in an AEP-specific private Codex home; AEP never extracts, copies, stores, returns or logs OAuth tokens.

Provider-specific mechanics belong behind provider adapters rather than spreading provider branches through the execution loop.

Model-provider credentials belong to Agent Execution Plane because it directly invokes the providers.

For `openai_chatgpt_oauth`, the model is selected from the Codex app-server catalogue. Removing one configured OAuth model does not log out the shared ChatGPT account.

## 8. Configured models and administrator priority

Each configured model includes at least:

- enabled/disabled state;
- explicit administrator-defined priority/order;
- provider/model technical configuration and credentials;
- a timeout covering that model's entire attempt on one execution.

Rules:

- every new execution starts again from the top of the administrator-defined priority list;
- disabled models are ignored;
- Execution Plane never automatically reorders, disables or quarantines models after failures;
- a priority-1 model that failed previously is tried again first on the next execution if still enabled and compatible;
- `disabled` means only that the administrator does not want the model used now.

Priority may be changed while a model is executing; the change affects only later executions.

While a model is executing the current job:

- it cannot be disabled;
- it cannot be deleted;
- its technical configuration cannot be changed in a way that could affect the current attempt;
- the UI clearly identifies it as currently in use.

A model not currently in use may be deleted whether enabled or disabled.

## 9. Model configuration validation

A new model cannot be saved until its initial technical validation succeeds, even when the model is initially disabled.

For an existing model configuration modification:

1. test the candidate configuration first;
2. apply it only if validation succeeds;
3. if validation fails, keep the previous valid configuration unchanged;
4. show a useful bounded error without exposing secrets.

Known tool/function-calling incompatibility prevents creation of a new model.

If an existing model later becomes incompatible, show `Incompatible`, exclude it from execution, and leave correction/removal to the administrator.

## 10. Model health

All configured models, enabled and disabled, are technically checked at application startup where possible.

Provider/model unavailability must never prevent the App itself from starting and must never mutate administrator priority or enabled/disabled state.

Periodic health checks are allowed only when they are guaranteed not to consume billable inference tokens, credits or provider quota.

No automatic health check may submit a prompt or trigger inference.

If a provider offers no guaranteed free/non-inferential health mechanism, no periodic check is performed; the UI may show an unverified/unknown state until a legitimate manual test or real execution updates it.

Health state is informational. Administrator priority remains authoritative for every new execution.

## 11. Single execution slot

Version one has exactly **one global execution slot**.

Execution Plane never executes two jobs concurrently and never owns an internal queue of waiting work.

With Agent Control Plane:

- when free and at least one enabled compatible model exists, poll ACP every **1 second**;
- if ACP is unavailable while idle, continue polling every **1 second** and expose the issue in the UI;
- when a job is claimed, stop claiming more work;
- resume polling immediately only after the current execution/result-delivery lifecycle is fully cleared;
- if no active compatible model exists, do not claim jobs and show a clear waiting state.

With the standalone API:

- if an execution is already active, `POST /execute` is refused immediately as busy;
- if a final result is still awaiting acknowledgement, `POST /execute` is also refused immediately;
- the caller is responsible for retrying later.

This is a worker loop, not a scheduler.

## 12. Model fallback

For every new execution, enabled compatible models are tried in administrator priority order.

Automatic fallback to the next model is allowed only after a **technical failure before any MCP tool action has actually executed**.

The fallback model starts completely from zero with:

- the original source-provided objective/input;
- the original frozen source-supplied MCP capability envelope;
- the original output contract;
- its own complete configured timeout.

No partial conversation, reasoning, summary or state from the failed model is passed to the fallback model.

Once any MCP action has actually executed, **no automatic fallback to another model is allowed** for that execution because side effects may already have occurred.

If all enabled compatible models fail technically before any MCP action, Execution Plane reports a bounded factual technical failure to the source. It does not schedule an internal retry later.

## 13. Per-model timeout

Each configured model has its own configurable timeout covering that model's **entire attempt** on the current execution.

Default for a newly configured model: **5 minutes**.

The administrator remains free to choose the timeout appropriate for each model. Agent Execution Plane does not derive or impose a product-level maximum from any caller's lease or lifecycle policy.

The timeout does not reset after each reasoning turn or tool call.

If timeout occurs before any MCP action executes, fallback may continue to the next model.

If timeout occurs after an MCP action has executed, no model fallback is allowed and the technical timeout is reported.

## 14. Agent Control Plane lease behavior

Execution Plane uses ACP's existing lease contract **only when ACP is the caller/source**.

Current ACP behavior:

- initial lease: **5 minutes**;
- heartbeat extends it in 5-minute windows;
- maximum attempt lifetime: **30 minutes**.

These values belong to ACP and do not define Agent Execution Plane's model-timeout policy. Another caller may expose different lifecycle limits or no lease mechanism at all.

A single transient communication/heartbeat failure does not immediately stop a running job. Execution may continue only while the already-issued lease remains unquestionably valid and heartbeat restoration is attempted.

As soon as lease validity can no longer be guaranteed:

- stop continuing the model attempt;
- issue no new MCP tool invocation;
- later report the factual interruption to ACP when communication permits.

ACP currently does not support manual cancellation of an already claimed job, so Execution Plane must not invent a separate claimed-job cancellation protocol.

## 15. Result delivery and acknowledgement

Execution Plane never owns more than one current execution/final result.

Once a final result exists, it is persisted until the destination explicitly accepts or acknowledges it.

While a final result is pending:

- no new execution is accepted or claimed;
- the model is not rerun;
- the same persisted result is retained;
- the UI clearly shows the pending-delivery state and any known technical cause.

### Agent Control Plane boundary

Execution Plane retries delivery to ACP every **1 second** until ACP accepts the result. Once accepted, the temporary local copy is deleted and polling resumes immediately.

### Standalone boundary

The standalone API is asynchronous:

- `POST /execute` submits the execution and returns an opaque execution ID;
- `GET /executions/<id>` retrieves state/result and **does not** release it;
- `POST /executions/<id>/ack` explicitly confirms successful receipt.

Only the explicit `ack` deletes the temporary local result and frees the execution slot.

The API/logs distinguish at least execution accepted, result available, result retrieved, result acknowledged and manual abandonment.

### Manual recovery

Both ACP and standalone operation expose an explicit confirmed **abandon pending result** administration action.

Abandonment deletes the local pending result and frees the engine. It does not rerun the model and does not decide what the source should do next.

## 16. Crash/restart safety and persistence

Persistence exists only for configuration and safe recovery, **not as a job database**.

Durable state includes only:

- model/provider configuration and credentials;
- application settings/source connection configuration;
- the minimum reference necessary to identify an execution that was active if the process restarts before a final result exists;
- a final result that exists but has not yet been accepted/acknowledged, plus the minimum delivery information required.

Execution Plane does not permanently store job histories, model conversations, reasoning histories or shadow copies of ACP governance state.

If the App restarts while a final result is pending, restore that exact result and continue waiting/delivery without rerunning the model.

If the App restarts while an execution was still running and no final result exists, **do not automatically rerun it**. Record/report the factual interruption to the source when possible; the source decides what happens next.

## 17. Standalone API boundary

Standalone operation is only a generic way for another source to use the **same execution engine** without Agent Control Plane.

The caller is the source authority for that standalone execution and supplies:

- `objective` / instruction;
- `input` JSON;
- MCP endpoint information;
- optional MCP credential required to access that endpoint;
- the exact model-invocable MCP capability envelope for that execution;
- optional JSON result schema.

The standalone caller is responsible for deciding what capability envelope it intends to expose. AEP does not inspect a broader MCP inventory and invent an authorization policy. It only verifies and executes the exact envelope supplied in the request.

The caller **never selects the model**. Execution Plane always applies its own configured model priority and fallback rules.

Execution Plane does not maintain a standalone connector catalog and does not reuse caller-supplied MCP endpoints, credentials or capability descriptors as configuration for later executions.

When a result schema is supplied, the final result must conform to that caller-provided output contract. When no result schema is supplied, free-form model output is allowed.

The exact JSON encoding/bounds of these fields remain technical API design, not a separate functional behavior.

### Standalone authentication

Standalone API access uses an **opaque Bearer token** managed by Agent Execution Plane, following the same credential philosophy as ACP:

- generated by the application;
- displayed to the administrator only once;
- never recoverable later in clear text;
- revocable and replaceable from the administration UI.

No separate username/password or session-login system is introduced.

The API documentation must clearly document submission, retrieval and acknowledgement, including the fact that failure to acknowledge intentionally keeps the single execution slot occupied.

## 18. MCP Capability Bridge independence

MCP Capability Bridge is optional.

If used, it is simply an MCP server whose tools may participate in a source-defined execution envelope, directly from a standalone caller or indirectly through Agent Control Plane's governed virtual capabilities.

Execution Plane must not know how Bridge capabilities are implemented internally and must not implement SSH, target HTTP, browser automation or appliance-specific execution itself.

## 19. Observability

Operational visibility is limited to what is required to operate and diagnose the execution engine, including:

- engine health;
- ACP/source connectivity where relevant;
- model state, priority, enabled/disabled state and compatibility;
- current technical execution activity;
- pending-result delivery/acknowledgement state;
- bounded/redacted technical errors;
- provider usage information where safely available.

Observability must not become a second governance/audit system and must not reinterpret model results.

## 20. Security baseline

Detailed design must preserve at least:

- least-privilege HAOS runtime and AppArmor policy;
- protected model-provider and source/MCP credentials;
- authenticated standalone API;
- bounded input/output and transport sizes;
- bounded MCP definitions, arguments and results;
- model/MCP timeouts required to prevent stuck execution;
- secret redaction/non-disclosure;
- no privileged shell/browser/target-HTTP side channel outside MCP;
- no model-produced data interpreted as configuration or new authorization;
- no capability broadening, selection or semantic authorization by Execution Plane;
- no source-boundary lifecycle tool exposed to the model merely because it exists on the same MCP server;
- crash/restart handling that never blindly replays potentially side-effecting work.

Security constrains the engine technically; it does not turn it into a business-policy engine.

## 21. HAOS application and user interface requirements

Agent Execution Plane is delivered as a **Home Assistant OS App** and must follow the same practical packaging discipline as Agent Control Plane.

Product requirements for the App shell are:

- installable and runnable as a normal HAOS App from the repository;
- a configurable **standalone API listener port** exposed through the App configuration rather than hard-coded as product policy;
- a mandatory least-privilege **AppArmor profile** appropriate to the actual runtime needs of Agent Execution Plane;
- a Home Assistant **Ingress administration interface** used to configure and operate the App without requiring direct access to the administration listener;
- an administration UI visually consistent with Agent Control Plane's graphical language and interaction style while remaining specific to Execution Plane's responsibilities;
- a fully bilingual **French/English** Ingress interface, with an in-UI language switch comparable to Agent Control Plane;
- full **light and dark mode** support, with an in-UI theme control comparable to Agent Control Plane;
- the application header displays **Agent Execution Plane** with the running application **version immediately beside the product name**, following the same presentation principle as Agent Control Plane;
- configuration/visibility for the models, their priority/state/timeout, the ACP source connection, standalone API credential/state, current execution state and pending-result recovery where applicable;
- repository App assets including a dedicated **logo** and **icon**;
- complete user documentation in both **English and French**, including installation, configuration, ACP integration and standalone API usage.

These are product requirements. The internal framework, database schema, process topology, listener implementation and AppArmor rules are implementation choices and do not require product-level administrator arbitration unless they change the visible behavior or security boundary above.

## 22. Non-goals

Agent Execution Plane must not:

- own ACP task definitions, triggers, schedules, events, incidents or policy;
- own or configure ACP upstream MCP connectors, connector inventories, endpoints or credentials;
- choose which MCP tools a governed ACP job is authorized to use;
- derive a model-visible capability set from the complete ACP `tools/list` inventory;
- reproduce ACP namespacing, virtual capability construction, `fixed_arguments_v1`, hidden argument injection or per-invocation authorization;
- expose ACP claim/heartbeat/complete/fail lifecycle tools to the reasoning model;
- duplicate ACP governance, retry policy, reports or audit logic;
- create its own scheduler or waiting-job queue;
- become a generic workflow/orchestration framework;
- classify model conclusions into business outcomes;
- decide source-level retry/escalation policy;
- add business instructions/context not supplied by the source;
- discover extra tools for a running execution and add them to the source envelope;
- execute direct infrastructure actions outside MCP;
- embed Home Assistant, Gatus, OpenDTU, Cerbo GX, UniFi or another product as core business logic;
- require Agent Control Plane or MCP Capability Bridge in order to run.

## 23. Genericity test

A proposed feature belongs in Agent Execution Plane only if it is required to:

> receive a source-supplied execution, apply the administrator-configured model execution order, execute it with exactly the model-invocable MCP capability envelope supplied by the source, and return the resulting model output or factual technical failure.

AEP may validate that this supplied contract is technically executable, but it never defines the authorization contract itself.

If a feature instead decides what work should exist, what capabilities should be authorized, how upstream connectors should be exposed/restricted, what a conclusion means operationally, or what should happen after the source receives the outcome, it belongs elsewhere.

## 24. Remaining detailed technical design

Remaining implementation work is intentionally technical rather than a second functional-design pass:

1. exact standalone JSON request/response encoding and size bounds for the already validated common execution contract;
2. provider-adapter interface for Ollama-compatible and OpenAI-compatible providers;
3. exact provider/tool-call mechanics and bounded structured-output validation;
4. exact MCP client/session mechanics, including strict separation between source-boundary lifecycle tools and the source-supplied model capability envelope;
5. model UI/provider-specific fields;
6. minimal persistence schema for active-interruption and pending-result recovery;
7. HAOS process/listener/network/AppArmor implementation consistent with the validated App requirements;
8. bounded logs, redaction and UI state presentation;
9. CI tests and real-HAOS acceptance gates.

These points must not reopen the validated execution behavior unless implementation reveals a concrete contradiction that cannot be resolved otherwise.

## 25. Delivery discipline

For every implementation lot:

`planned -> implemented by Codex -> independently reviewed -> CI validated -> deployed on HAOS -> real acceptance tested -> accepted`

A Codex summary alone never marks a lot complete. Any defect found during review or HAOS acceptance is patched, reviewed and retested before the lot is accepted.