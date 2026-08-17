# HAOS App Common Conventions

Status: **normative shared convention** for new Home Assistant OS Apps in this repository unless a narrower project document explicitly requires otherwise.

This document centralizes practical HAOS requirements that are common across projects and should not be re-decided independently for every App. It currently applies to Agent Execution Plane and MCP Capability Bridge and should be considered for future HAOS Apps added to the repository.

## Runtime log timestamps

Runtime logs visible from the Home Assistant App log view must be timestamped whenever the emitting component is under the App's control.

Requirements:

- application-generated log lines use a timezone-aware **ISO 8601** timestamp;
- the timestamp includes an explicit UTC offset (or `Z` when UTC is the only available timezone), and must never be timezone-naive;
- when the HAOS/container local timezone is available, it is preferred so logs correlate naturally with Home Assistant and local infrastructure events;
- application log lines should also identify the product and severity in a compact form, following the established Agent Control Plane style where practical, for example:
  - `2026-08-17T01:02:04+02:00 [Agent Execution Plane] INFO: ...`
  - `2026-08-17T01:02:04+02:00 [MCP Capability Bridge] INFO: ...`;
- Uvicorn and other runtime/library logs whose formatter can be controlled by the App must also receive timezone-aware timestamps;
- third-party library output that is routed through Python logging should use the common formatter where practical;
- logging configuration must avoid accidentally adding two timestamps to a line that is already formatted by a lower layer;
- secret-redaction requirements remain authoritative: timestamps must not encourage logging request bodies, credentials, model reasoning, browser page contents, SSH output or other sensitive payloads.

Early service-manager messages that are emitted by the Home Assistant base image before the application logging stack is active are exempt. In particular, lines such as:

` s6-rc: info: service ... `

may remain in their native un-timestamped form.

The objective is that once the App's own startup begins, operational log lines can be correlated precisely in time without pretending that pre-application `s6-rc` output is controlled by the project.

## Ingress operational activity journal

Each App must also provide a **persistent, human-readable operational activity journal in its Ingress UI**. This journal is distinct from the Home Assistant App runtime log above.

Its purpose is to answer, at a glance: **what has this App been doing?** It is not a business audit ledger, a model-conversation history, a target-session recording or a replacement for HAOS runtime logs.

### Common behavior

- the UI exposes a dedicated bilingual **Activity / Activité** view or an equivalently clear product-specific view;
- every entry has a timezone-aware ISO 8601 timestamp and a stable machine-readable event/category code behind the translated UI text;
- entries survive normal App restarts;
- retention is intentionally bounded: initial default is **30 days or 10,000 entries, whichever limit is reached first**;
- pruning removes oldest entries automatically and must never block normal App operation;
- the journal is paginated/bounded in the UI and may provide simple filters such as category/status without becoming an analytics product;
- when a public/API/MCP transport provides a meaningful remote peer address, the safe source IP may be recorded and displayed;
- connection/session open/close events are recorded only where the application/protocol actually has meaningful session lifecycle information; the App must not invent a fake TCP-style “disconnect” event for stateless request traffic;
- successful and rejected authentication/access events may record the safe peer IP and outcome, but never the presented credential;
- configuration changes may be recorded as safe actions such as model/target added, disabled, edited or credential rotated, without storing the changed secret or sensitive payload;
- the journal remains an operational timeline, not a hash-chained authorization audit system like Agent Control Plane's governance audit.

### Data that must never appear

The journal must never store or display:

- Bearer/API tokens, authorization headers or token/verifier material;
- passwords, private keys, passphrases, cookies or browser/session credentials;
- model prompts, reasoning/thinking content, source objective/input payloads or final model result bodies;
- MCP tool arguments or MCP tool result bodies;
- browser page text, DOM/HTML snapshots, screenshots, form values, local/session storage or browsing history;
- SSH command argument values, stdin, stdout or stderr;
- raw request/response bodies;
- stack traces or unredacted upstream exceptions;
- any secret value merely because it was present in configuration or transport metadata.

Safe identifiers such as product-controlled model names, target names, adapter types, MCP tool names, execution/session correlation IDs, status categories and durations may be recorded where useful.

### Agent Execution Plane activity

At minimum, Agent Execution Plane should journal safe lifecycle events such as:

- App start/stop/readiness and source connectivity changes;
- standalone/API authentication accepted/rejected with safe peer IP where available;
- execution accepted/claimed/refused-busy/interrupted;
- selected model attempt start/success/technical failure/timeout and fallback to the next configured model;
- MCP tool dispatch/completion/failure using **tool name only**, never arguments/results;
- final result becoming pending, delivery attempts/outcome, standalone retrieval/acknowledgement and manual abandonment;
- safe model/source/API configuration changes and credential rotation events.

This does **not** create a completed-job history: no objective, input, model conversation, reasoning, tool payload or result body is retained in the journal.

### MCP Capability Bridge activity

At minimum, MCP Capability Bridge should journal safe lifecycle events such as:

- App start/stop/readiness;
- MCP authentication accepted/rejected with safe peer IP where available;
- meaningful MCP client/session lifecycle events where the negotiated transport exposes them;
- MCP tool invocation start/completion/failure with safe **tool name**, adapter type, configured target name, status and duration only;
- Web session open/close/expiry/cleanup without page content, cookies or form values;
- SSH invocation connection/start/completion/failure/close without command arguments or stdout/stderr;
- safe target/adapter configuration changes and credential rotation events.

This journal must not defeat the Bridge's stateless-session policy: Web browsing artifacts and SSH invocation contents remain disposable even though a small safe activity record is retained.

### Persistence distinction

Project documents that prohibit permanent job history, invocation history, browser history or reasoning history remain valid. The bounded activity journal defined here is explicitly **safe operational metadata only** and is not permission to persist the corresponding payloads or semantic histories.

## Validation

For each new App, the executable HAOS shell lot must configure timestamped runtime logging **and the initial Activity/Activité journal plumbing/view from the start**. Early shell events may include only App startup/readiness/configuration activity; later implementation lots add their own safe product-specific event types as the corresponding functionality becomes real.

CI/container smoke tests should assert representative timestamps for application-generated logs and configurable server-runtime logs where stable testing is practical. CI must also verify journal persistence/pruning and representative secret non-disclosure cases.

Real HAOS acceptance must verify that normal startup logs show useful timezone-aware timestamps after the native `s6-rc` preamble, and that the Ingress activity journal survives a normal restart without exposing sensitive data.
