# MCP Capability Bridge — Implementation Plan

Status: **authoritative implementation sequence — implementation not started**.

This plan is derived from `PROJECT_BRIEF.md`, `TECHNICAL_DESIGN.md` and the root `ARCHITECTURE_CHARTER.md`.

The plan is finite. Product scope is fixed; implementation lots must not reopen it unless code/HAOS evidence exposes a contradiction that cannot be solved within the validated boundary.

For every lot:

`planned -> implemented -> independently reviewed -> CI conformant -> deployed on HAOS -> real acceptance tested -> accepted`

Codex implements one bounded lot at a time. A Codex summary is not acceptance evidence.

## Global invariants

Every lot must preserve:

- independent generic MCP server; no required Agent Control Plane or Agent Execution Plane dependency;
- adapter-oriented core; Web and SSH are initial adapters only;
- no reasoning models, tasks, jobs, leases, schedules or workflow engine;
- standard MCP Streamable HTTP only;
- one Bridge-owned opaque Bearer credential initially;
- target identity and credentials remain administrator-controlled;
- target secrets remain inside the Bridge;
- no durable invocation queue/history or automatic replay/retry;
- **runtime target sessions are disposable**;
- each Web session starts clean and leaves no reusable browser state after close/expiry/restart;
- each SSH tool invocation uses a fresh connection and leaves no persistent SSH session/output history;
- unprivileged HAOS runtime and least-privilege AppArmor;
- configurable MCP host port through HAOS Network settings;
- Ingress UI follows ACP visual language, FR/EN, light/dark, product name + version;
- dedicated icon/logo and FR/EN documentation;
- appliance names never become core logic.

## Lot 0 — executable HAOS App shell

Status: **planned**.

### Goal

Create the smallest real MCP Capability Bridge HAOS App that installs, starts and exposes a safe administration shell before MCP tools or adapters exist.

### Scope

- HAOS App metadata under `mcp_capability_bridge/`;
- initial version source and `MCP Capability Bridge vX.Y.Z` header;
- Home Assistant base image and provenance discipline comparable to ACP;
- unprivileged runtime user;
- startup/graceful-shutdown foundation;
- SQLite generation-1 initialization plumbing;
- Ingress listener `8099`;
- public/MCP listener foundation `8098`, with configurable HAOS host-port mapping;
- non-sensitive `/health/live` and `/health/ready`;
- first least-privilege AppArmor profile from actual runtime inventory;
- ACP-style Ingress shell;
- FR/EN and light/dark controls;
- Overview showing only real App readiness;
- initial logo/icon;
- basic FR/EN installation docs;
- dedicated GitHub Actions workflow;
- image/listener/restart/persistence/AppArmor smoke tests.

### Anti-goals

No MCP tools, Bearer issuance, targets, browser, SSH, adapter implementation or fake/sample tools.

### HAOS acceptance

Install, confirm clean logs/startup, verify Ingress/version/language/theme, verify configurable 8098 host port, restart App and HAOS cleanly.

## Lot 1 — authenticated MCP server and generic adapter foundation

Status: **planned**.

### Goal

Create the real standalone MCP endpoint, secure target persistence and generic adapter registration without implementing target operations yet.

### Scope

- exact stable official MCP Python SDK v2 pin;
- Streamable HTTP `/mcp`;
- compatibility with current and ACP-era MCP clients on one endpoint;
- tools-only MCP surface;
- opaque Bearer issue/replace/revoke lifecycle;
- one-time token display and verifier-only storage;
- App-local secret-encryption key under `/data/private`;
- encrypted reversible target-secret utilities;
- generic target persistence: stable key, display name, adapter type, enabled state, bounded config envelope, encrypted secret payload;
- internal adapter registration interface for validation/tool definition/invocation/cleanup/status;
- bounded global concurrency accounting foundation;
- Ingress MCP access + Targets views;
- deterministic empty tool inventory until adapters are implemented;
- no fake/echo tool.

### CI evidence

Prove authenticated MCP discovery, old-token invalidation, no clear token recovery, encrypted secret persistence, target CRUD/restart persistence, empty tool inventory and adapter registration tests with test doubles only.

### HAOS acceptance

Issue/rotate MCP token, connect generic client, confirm empty authenticated tool list, create/restart/delete a disabled target, confirm no secret disclosure.

## Lot 2 — interactive Web administration adapter

Status: **planned**.

### Goal

Let a tool-calling model operate administrator-configured HTTP/HTTPS administration interfaces through short-lived isolated browser sessions.

### Browser implementation gate

Do **not** hard-code Chromium as a product requirement.

Start with the simplest HAOS-proven candidate, expected to be system Chromium + ChromeDriver/Selenium because Alpine packages them together and temporary clean profiles are naturally supported.

If Firefox/geckodriver or another standards-compatible stack proves cleaner under real HAOS/AppArmor testing, it may be used instead without changing the MCP contract.

The lot is not accepted if the chosen engine requires privileged mode, broad host filesystem/device access or an unjustifiably broad AppArmor profile.

### Scope

- Web target with fixed HTTP/HTTPS origin, allowed origins, TLS policy, enabled state and encrypted auth material;
- initial auth modes: none, HTTP Basic, bounded configured form login;
- target-scoped Web MCP tool family equivalent to open/snapshot/navigate/click/fill/select/press/wait/screenshot/close;
- text/accessibility snapshot with Bridge-issued opaque element references;
- no model-supplied selectors or arbitrary JavaScript;
- no arbitrary URL/origin escape;
- no uploads/downloads or filesystem access;
- no DevTools/remote-control surface;
- bounded session concurrency, inactivity TTL and absolute lifetime;
- optional screenshot path, text path normative;
- AppArmor extended only for proven browser runtime requirements.

### Disposable-session rule

Every `web_open` creates a **fresh isolated session**.

The session may span several MCP calls, but:

- no cookies, history, cache, localStorage, sessionStorage, IndexedDB or browser profile are loaded from a previous session;
- no browser storage state is exported for later reuse;
- no HAR/video/trace archive is retained in normal operation;
- temporary profile/context exists only for that runtime session;
- close, expiry, browser failure, App shutdown or restart destroys it;
- a new session to the same target must start clean again.

### CI evidence

Use a deterministic local Web fixture to prove:

- configured login works without exposing credentials;
- non-vision text/tool-calling path works end to end;
- element refs work and stale refs fail safely;
- allowed navigation works and origin escape is blocked;
- two consecutive sessions to the same target do **not** share cookies/storage/history/login state except where the Bridge explicitly logs in again using stored target credentials;
- no reusable profile/storage file remains after close;
- forced browser crash/timeout cleans the session;
- App restart invalidates all handles and leaves no restored browser session;
- browser runtime remains within accepted AppArmor boundary.

### HAOS acceptance

Configure a harmless administration fixture, open/use/close a session, confirm stored login remains invisible, then open a second session and verify it starts clean. Restart App/HAOS and verify no browser process/session/state returns.

## Lot 3 — bounded SSH adapter

Status: **planned**.

### Goal

Expose bounded SSH operations as MCP tools with a fresh connection for every invocation and no persistent remote session.

### Scope

- SSH target with fixed host/IP, port, username, enabled state, encrypted credential and mandatory pinned/trusted host key;
- connectivity/authentication/host-key test without arbitrary remote command;
- bounded SSH capability definitions with stable MCP tool name, strict input schema, fixed command head, ordered literal/input argument template, timeout and output bounds;
- safe argument construction;
- no whole caller command string;
- no PTY, arbitrary env map or unrestricted stdin;
- no automatic retry;
- Ingress SSH capability CRUD/test/status;
- target/capability in-use mutation protection.

### Disposable-connection rule

For every SSH `tools/call`:

`open new connection -> authenticate + verify host key -> execute one bounded command -> collect bounded result -> close connection`

Do not retain or reuse connection/session handles, shells, PTYs, multiplexing, agent-forwarding state, remote working directories, command history, arguments, stdout or stderr between calls or in persistent storage.

Only administrator target/capability configuration, encrypted credential and trusted host-key material remain durable.

### CI evidence

Use a deterministic local SSH fixture to prove:

- a new connection is established per invocation;
- the prior connection is closed after success, failure and timeout;
- no shell/PTY/multiplex state survives between calls;
- host-key validation fails closed;
- argument injection remains data rather than syntax;
- secrets, arguments and stdout/stderr are absent from persistent DB/history/logging paths;
- output/time bounds and no automatic retry.

### HAOS acceptance

Against a restricted test account, call a harmless bounded command twice and verify each invocation is independent, credentials stay hidden, no shell state carries over and disabled capability disappears from discovery.

## Lot 4 — hardening, interoperability, documentation and production cutoff

Status: **planned**.

### Goal

Close the first production-ready release after Web and SSH are accepted on real HAOS.

### Scope

- complete threat-model review;
- finalized hard resource limits;
- concurrency/busy tests;
- malformed/oversized MCP cases;
- forced browser/SSH failure cleanup;
- repeated Web session isolation/leak tests;
- repeated SSH connection-isolation tests;
- graceful shutdown verification;
- credential rotation safety;
- polished bilingual Ingress UI;
- final logo/icon;
- complete README/README.fr/HAOS docs;
- generic MCP client examples;
- ACP interoperability through ordinary MCP only;
- supported architecture image builds where repository infrastructure permits;
- real AppArmor HAOS startup/use/shutdown/restart acceptance;
- declare production-data preservation cutoff.

### Release invariants

Before production cutoff:

- Bridge works without ACP/Execution Plane;
- adding a future adapter does not require core redesign;
- Web works through text/tool calling without model-specific Browser mode;
- no Web runtime state survives session destruction or restart;
- every SSH invocation is connection-isolated and leaves no persistent runtime/output state;
- clients cannot change configured target identity;
- credentials are never disclosed;
- no automatic operation replay/retry exists;
- no permanent invocation/session history exists.

### HAOS acceptance

Perform clean install/UI/auth checks, Web end-to-end including second-session clean-state proof, SSH end-to-end including fresh-connection proof, generic client + ACP discovery/calls, restart during/after Web activity, persistence of configuration only, and AppArmor denial-free normal operation without unjustified permissions.

After acceptance, target/credential/SSH-capability configuration is production data. Future schema evolution requires explicit deterministic tested migrations.

## Delivery discipline

For each lot, derive one precise Codex instruction from this plan. After Codex pushes, independently inspect actual diff/code/tests and CI; request focused micro-patches only for real defects/drift; deploy only conformant code; run HAOS acceptance one practical step at a time; mark the lot accepted only after real HAOS success.
