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

## Validation

For each new App, the executable HAOS shell lot must configure this logging behavior from the start. CI/container smoke tests should assert representative timestamps for application-generated logs and for configurable server-runtime logs where stable testing is practical.

Real HAOS acceptance must also verify that normal startup logs show useful timezone-aware timestamps after the native `s6-rc` preamble.
