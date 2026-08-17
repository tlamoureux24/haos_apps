# MCP Capability Bridge — Implementation Plan

Status: **authoritative implementation sequence — implementation not started**.

This plan is derived from `PROJECT_BRIEF.md`, `TECHNICAL_DESIGN.md` and the root `ARCHITECTURE_CHARTER.md`.

The plan is finite. Product scope is already fixed; implementation lots must not reopen it unless code/HAOS evidence reveals a contradiction that cannot be solved within the validated boundary.

For every lot:

`planned -> implemented -> independently reviewed -> CI conformant -> deployed on HAOS -> real acceptance tested -> accepted`

Codex implements one bounded lot at a time. A Codex summary is never acceptance evidence by itself.

## Global invariants

Every lot must preserve:

- MCP Capability Bridge is an independent generic MCP server;
- no required Agent Control Plane or Agent Execution Plane dependency;
- no reasoning models, jobs, tasks, leases, schedules or workflow engine;
- targets/capabilities are administrator-owned technical configuration;
- enabled valid capabilities are ordinary MCP tools;
- MCP arguments cannot replace target identity, credentials or hidden fixed configuration;
- no default unrestricted SSH command, arbitrary URL proxy or arbitrary browser-control tool;
- one Bridge-owned opaque Bearer credential authenticates the MCP endpoint, without per-client business permissions;
- target secrets are reversible only inside the Bridge and never exposed after storage;
- no durable invocation-history database or retry queue;
- no automatic replay/retry of target operations;
- standard MCP Streamable HTTP contracts only;
- current MCP 2026-07-28 support plus 2025-era client compatibility on the same endpoint through MCP Python SDK v2;
- unprivileged HAOS runtime, least-privilege AppArmor and bounded resources;
- configurable MCP host port through HAOS Network settings;
- Ingress UI follows ACP visual language, FR/EN, light/dark, product name + version;
- dedicated icon/logo and FR/EN documentation;
- product/appliance names never become core logic.

## Lot 0 — executable HAOS App shell

Status: **planned**.

### Goal

Create the smallest real MCP Capability Bridge HAOS App that installs, starts and exposes its administration shell safely, without pretending adapter functionality exists yet.

### Scope

- complete HAOS App metadata under `mcp_capability_bridge/`;
- initial version source and `MCP Capability Bridge vX.Y.Z` header;
- Dockerfile based on the Home Assistant base image with pinned-build/provenance discipline comparable to ACP;
- unprivileged `mcp-capability-bridge` runtime user;
- startup script and graceful signal handling foundation;
- SQLite generation-1 initialization plumbing with only infrastructure needed by later lots;
- fixed internal administration listener on `8099` through Home Assistant Ingress;
- fixed internal MCP/public listener on `8098`, exposed through a user-configurable HAOS Network host-port mapping;
- non-sensitive `/health/live` and `/health/ready`;
- first least-privilege AppArmor profile based on the actual shell/runtime executable inventory;
- Ingress shell visually aligned with ACP;
- FR/EN language switch;
- light/dark theme switch;
- Overview page showing App readiness and clearly showing that MCP access/targets/capabilities are not configured yet;
- dedicated initial logo/icon assets;
- basic FR/EN installation documentation;
- dedicated GitHub Actions workflow;
- image build, listener-isolation and restart/persistence smoke tests.

### Anti-goals

Do not implement MCP tool discovery/calls, Bearer issuance, targets, capabilities, HTTP, SSH, Browser, fake sample tools or appliance-specific placeholders.

### CI evidence

- metadata/source validation;
- dependency install, compile and unit tests;
- amd64 image build with base-image provenance artifact;
- startup and health endpoints;
- Ingress-prefix correctness;
- bilingual/theme/version UI assertions;
- no normal host exposure of administration listener;
- configurable published 8098 port metadata;
- restart/persistent `/data` smoke test;
- AppArmor executable inventory.

### HAOS acceptance

1. install from repository;
2. confirm clean startup/logs;
3. open Ingress and verify product name + version;
4. verify FR/EN;
5. verify light/dark;
6. verify the MCP host port can be changed in Home Assistant Network configuration;
7. restart App and HAOS and confirm clean recovery.

Lot 0 proves only the HAOS shell/security foundation.

## Lot 1 — authenticated MCP server and generic configuration core

Status: **planned**.

### Goal

Turn the shell into a real standalone MCP server with secure access and generic target/capability persistence, while still exposing no technical capability until an adapter exists.

### Scope

- exact stable MCP Python SDK v2 pin chosen at implementation time;
- Streamable HTTP endpoint `/mcp`;
- modern MCP 2026-07-28 request support;
- legacy/2025-era MCP compatibility on the same endpoint;
- tools-only server surface;
- Bridge Bearer credential issue/replace/revoke lifecycle;
- one-time clear token display;
- verifier-only token persistence with App-local pepper/HMAC key under `/data/private`;
- reject unauthenticated MCP requests;
- reject unsafe browser `Origin` requests;
- `targets` and `capabilities` generation-1 persistence tables;
- App-local authenticated-encryption key for reversible target secrets;
- encrypted secret storage utilities and strict redaction helpers;
- generic target/capability repositories and static validation;
- globally unique stable MCP tool names;
- enabled/disabled state and in-use snapshot/locking infrastructure;
- bounded global invocation semaphore infrastructure, default 4;
- administration views for MCP access, Targets and Capabilities;
- capability schema validation/bounds;
- `tools/list` returns a deterministic empty list because no adapter capability type is implemented yet;
- no fake/echo demonstration tool.

### Anti-goals

Do not implement HTTP requests, SSH connections, Browser processes, Control Plane-specific auth or per-client permissions.

### CI evidence

- modern MCP discovery/list behavior;
- legacy client discovery/list behavior against the same endpoint;
- Bearer required/fail-closed;
- replacement invalidates old token;
- clear token never recoverable via API/database/logs;
- encrypted target-secret round-trip without plaintext persistence;
- target/capability validation tests;
- concurrent capacity/busy primitive tests;
- Ingress CRUD shell tests with no fake tools.

### HAOS acceptance

1. upgrade/install cleanly;
2. issue MCP credential and copy it once;
3. verify it is no longer displayable after leaving the one-time view;
4. connect with a compatible MCP client and confirm authenticated empty `tools/list`;
5. verify wrong/old token is rejected after rotation;
6. create a disabled placeholder target/capability configuration only where the UI can validate generic fields without adapter execution, then confirm restart persistence and no secret disclosure.

Lot 1 establishes the server/security/configuration foundation.

## Lot 2 — bounded HTTP adapter

Status: **planned**.

### Goal

Make the Bridge useful for generic HTTP(S) targets without becoming an arbitrary URL proxy.

### Scope

- `http` target type with:
  - administrator-fixed base URL/origin;
  - TLS verification policy defaulting enabled;
  - optional basic/bearer credential;
  - optional fixed non-secret/secret headers;
  - encrypted secret storage;
- bounded HTTP target connection test that does not execute a configured capability operation;
- HTTP capability type with:
  - fixed method;
  - fixed relative path template;
  - explicit path/query argument mappings;
  - optional fixed JSON body plus explicit input-to-body mappings;
  - protected fixed headers;
  - per-capability timeout, default 30 seconds;
  - per-capability bounded output limit;
- redirects disabled;
- strict URL encoding and no caller-controlled scheme/host/port;
- JSON/text bounded response normalization;
- safe technical HTTP/transport errors;
- no secret response headers returned;
- explicit capability-test action in Ingress with side-effect warning;
- `tools/list` exposes enabled valid HTTP capabilities as ordinary MCP tools;
- `tools/call` validates exact schema before HTTP dispatch;
- no automatic HTTP operation retry.

### Anti-goals

No arbitrary caller URL, arbitrary caller headers, generic reverse proxy, HTML browser automation, product-specific API code or Control Plane policy.

### CI evidence

Use a local deterministic HTTP fixture to prove:

- normal GET/POST mapping;
- path/query/body argument encoding;
- auth/fixed secret injection without disclosure;
- caller cannot override host/origin/auth;
- redirect is not followed;
- TLS policy code paths;
- timeout;
- oversized result fails boundedly;
- unexpected argument rejection;
- tool schema/result behavior under modern and legacy MCP clients;
- disabled/invalid capability omitted from `tools/list`;
- no automatic duplicate request after failure.

### HAOS acceptance

Create one harmless local HTTP target/capability and validate:

1. target/capability appears correctly in bilingual UI;
2. MCP client discovers only the configured tool;
3. valid call reaches the fixed target and returns bounded result;
4. invalid argument/attempted target escape is rejected before target execution;
5. secret is never visible in UI/log/MCP result;
6. disable capability and confirm it disappears from discovery;
7. restart App/HAOS and confirm configuration persists.

Lot 2 proves the first real standalone Bridge use case.

## Lot 3 — bounded SSH adapter

Status: **planned**.

### Goal

Expose administrator-defined SSH operations without providing an unrestricted remote shell.

### Scope

- `ssh` target type with:
  - fixed host/IP;
  - port;
  - username;
  - mandatory pinned host-key trust material;
  - encrypted private-key/password authentication;
  - encrypted private-key passphrase where used;
- explicit connect/auth/host-key test without remote command execution;
- SSH capability type with:
  - fixed executable/command head;
  - ordered argv template of fixed literals and declared input properties;
  - no caller-controlled whole command;
  - no PTY;
  - no arbitrary environment map;
  - no unrestricted stdin in this release;
  - POSIX-safe argument construction;
  - timeout/output bounds;
- normalized exit-code/stdout/stderr result;
- deterministic transport/host-key/auth/timeout errors;
- explicit capability-test action with side-effect warning;
- no automatic SSH command retry.

### Anti-goals

No generic `ssh_exec(command)`, interactive shell, terminal, SCP/SFTP, arbitrary caller user/host/key, automatic sudo semantics or product-specific SSH command library.

### CI evidence

Use an in-process/local AsyncSSH fixture to prove:

- correct pinned-host connection;
- wrong host key fails closed;
- auth failure;
- fixed command + mapped arguments;
- shell-metacharacter/injection argument remains one quoted argument;
- caller cannot alter host/user/command head;
- non-zero exit reporting;
- timeout;
- oversized stdout/stderr bounded failure;
- no PTY;
- no retry after ambiguous/disconnected execution;
- secret non-disclosure;
- MCP modern/legacy discovery/call compatibility.

### HAOS acceptance

Use a deliberately restricted SSH test account and one harmless fixed capability:

1. verify target host-key pinning and auth test;
2. discover tool from an MCP client;
3. execute valid capability;
4. pass hostile shell characters as an argument and verify they remain data rather than shell syntax;
5. verify wrong/unexpected argument fails before SSH execution;
6. verify credential remains hidden;
7. disable/delete when idle and confirm discovery changes;
8. restart and confirm persistence.

Lot 3 establishes the HTTP+SSH practical production baseline.

## Lot 4 — bounded Browser adapter

Status: **planned, security-gated**.

### Goal

Support technical web interfaces that cannot reasonably be used through the HTTP adapter, without exposing generic remote browser control.

### Entry gate

Before implementation, Codex must verify that a specific pinned Chromium + Python browser-driver combination works reproducibly inside the Home Assistant base image on supported architectures. If the selected stack cannot be made reliable without privileged container access or broad AppArmor exceptions, stop this lot and report the concrete blocker instead of weakening the App security boundary.

This is a technical feasibility gate, not a reason to alter the already accepted HTTP/SSH product.

### Scope

- add system/headless Chromium and pinned driver library only in this lot;
- `browser` target type with:
  - fixed base origin;
  - optional explicit same-target allowed origins;
  - encrypted named secret values;
  - TLS policy;
- one-browser-invocation concurrency bound initially;
- isolated temporary browser profile/context per invocation;
- bounded browser capability step sequence supporting only:
  - fixed relative navigation;
  - fixed-selector wait;
  - fixed-selector fill from literal, declared argument or named target secret;
  - fixed-selector click;
  - fixed-selector select;
  - fixed-selector text extraction;
  - fixed-selector fixed-attribute extraction;
- timeout and deterministic process/profile cleanup;
- bounded extracted result map;
- adapter-specific AppArmor extension based on trace and actual runtime needs.

### Anti-goals

No arbitrary JavaScript, caller-provided URL/origin/selector, DevTools remote control, generic browsing tool, download/upload, filesystem browsing, screenshot/whole-page dump by default, persistent unrestricted profile or hidden browser side channel.

### CI evidence

Use a local deterministic web fixture to prove:

- Chromium starts headlessly in the built image;
- same-origin navigation succeeds;
- forbidden origin escape fails;
- argument and target-secret fill work without secret disclosure;
- caller cannot change selectors/URL;
- extraction result is bounded;
- timeout terminates browser child processes;
- temporary profile removed;
- multiple Browser calls respect stricter concurrency;
- AppArmor executable/file inventory covers only proven requirements.

### HAOS acceptance

On HAOS, with a harmless local web fixture:

1. create Browser target/capability;
2. execute bounded interaction and extraction;
3. verify origin/selector escape attempts fail;
4. verify secret never appears in result/log/UI;
5. verify timeout/failed page leaves no stuck Chromium processes;
6. restart App and HAOS cleanly;
7. inspect logs for AppArmor denials.

Browser is accepted only if all of the above pass without privileged-mode or broad host access.

## Lot 5 — release hardening, interoperability and production cutoff

Status: **planned**.

### Goal

Close MCP Capability Bridge as a coherent production App after all adapter lots accepted.

### Scope

- full review against Project Brief/Technical Design/Architecture Charter;
- verify no suite-private coupling or appliance-specific core logic;
- verify modern MCP 2026-07-28 behavior and legacy 2025 compatibility on same endpoint;
- explicit real interoperability test with Agent Control Plane as an ordinary MCP connector:
  - discovery;
  - stable capability schema;
  - capability invocation through ACP's normal governed surface;
  - no Bridge-specific ACP code;
- direct standalone MCP-client acceptance independent of ACP/Execution Plane;
- concurrency/busy/resource exhaustion tests;
- graceful shutdown with active HTTP/SSH and Browser calls;
- complete secret/redaction review;
- AppArmor final trace/inventory and HAOS denial review;
- backup/restore behavior for Bridge-owned `/data`;
- complete FR/EN README/DOCS/API/MCP/adapter security documentation;
- dedicated logo/icon finalization if required;
- CI provenance artifacts and full smoke/integration suite;
- declare production-data preservation cutoff once HAOS acceptance succeeds.

### Anti-goals

No new adapters, workflow language, per-client authorization, audit platform or feature expansion during release hardening.

### CI evidence

- complete unit/integration suite;
- image build/provenance;
- modern + legacy MCP contract tests;
- HTTP/SSH/Browser fixtures;
- full authentication/secret/redaction matrix;
- listener isolation;
- graceful shutdown/restart;
- AppArmor inventory;
- no plaintext secret search in persisted database/log fixtures;
- deterministic tools inventory;
- standard MCP interoperability fixture equivalent to ACP discovery/call expectations.

### HAOS acceptance

Perform one final clean installation before the production cutoff, then:

1. clean startup with zero targets/capabilities;
2. validate Ingress FR/EN/light/dark/version and configurable MCP port;
3. issue MCP token and connect standalone client;
4. configure/accept one HTTP capability;
5. configure/accept one SSH capability;
6. configure/accept Browser capability if Lot 4 passed its security gate;
7. connect ACP as an ordinary MCP connector and discover/call a selected Bridge tool through normal ACP governance;
8. restart App and HAOS with configuration retained;
9. verify backup/restore if practical in the acceptance environment;
10. confirm no AppArmor denials or secret leakage.

After this acceptance, declare the Bridge production-data preservation cutoff. From that point onward, target/capability/credential data is non-disposable and schema changes require deterministic tested migrations.

## Delivery discipline after implementation begins

For each lot:

1. derive one Codex prompt from this plan;
2. Codex implements **only that lot** and pushes its commit/CI;
3. independently inspect actual diff/code/tests/CI;
4. issue only focused micro-patches for concrete defects/drift;
5. re-review until conformant;
6. deploy to HAOS only after code review and green CI;
7. run the lot's real HAOS acceptance one step at a time;
8. patch/review/redeploy/retest any defect;
9. mark the lot accepted only after successful HAOS evidence;
10. then move to the next lot.

The existence of later planned lots must never justify prematurely implementing their code in the current lot.