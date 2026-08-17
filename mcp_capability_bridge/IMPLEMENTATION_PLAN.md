# MCP Capability Bridge — Implementation Plan

Status: **authoritative implementation sequence — implementation not started**.

This plan is derived from `PROJECT_BRIEF.md`, `TECHNICAL_DESIGN.md` and the root `ARCHITECTURE_CHARTER.md`.

The plan is finite. Product scope is fixed; implementation lots must not reopen it unless code/HAOS evidence exposes a contradiction that cannot be solved within the validated boundary.

For every lot:

`planned -> implemented -> independently reviewed -> CI conformant -> deployed on HAOS -> real acceptance tested -> accepted`

Codex implements one bounded lot at a time. A Codex summary is not acceptance evidence.

## Global invariants

Every lot must preserve:

- MCP Capability Bridge is an independent generic MCP server;
- no required Agent Control Plane or Agent Execution Plane dependency;
- no reasoning models, jobs, tasks, leases, schedules or workflow engine;
- the Bridge core is adapter-oriented and must allow future bounded target types without redesigning MCP/authentication or unrelated adapters;
- **Web** and **SSH** are the only adapters in the initial implementation plan, not permanent product limits;
- Web administration means interactive model access to configured HTTP/HTTPS administration interfaces through Bridge-driven browser tools;
- the model does not require native Browser support, only ordinary tool/function calling from its host;
- SSH remains bounded and never exposes a default unrestricted shell;
- caller input cannot replace administrator-controlled target identity or credentials;
- browser actions cannot escape configured top-level origins;
- browser actions use Bridge-issued element references rather than arbitrary model-supplied selectors;
- target secrets remain inside the Bridge;
- one Bridge-owned opaque Bearer credential authenticates the MCP endpoint without per-client business permissions;
- no durable invocation queue/history or automatic replay/retry;
- standard MCP Streamable HTTP only;
- same endpoint must interoperate with current MCP clients and the earlier MCP generation used by ACP;
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
- Dockerfile based on Home Assistant base image with provenance discipline comparable to ACP;
- unprivileged runtime user;
- startup and graceful signal-handling foundation;
- SQLite generation-1 initialization plumbing;
- fixed internal Ingress administration listener `8099`;
- fixed internal public/MCP listener `8098`, exposed through user-configurable HAOS host-port mapping;
- non-sensitive `/health/live` and `/health/ready`;
- initial least-privilege AppArmor based on actual executable inventory;
- Ingress shell visually aligned with ACP;
- FR/EN switch;
- light/dark switch;
- Overview showing only real App readiness;
- dedicated initial logo/icon;
- basic FR/EN installation documentation;
- dedicated GitHub Actions validation workflow;
- image build, listener-isolation, restart/persistence and AppArmor-inventory smoke tests.

### Anti-goals

Do not implement MCP tool discovery/calls, Bearer issuance, targets, any technical adapter or fake tools.

### CI evidence

- metadata/source validation;
- exact dependency installation;
- Python compile/unit tests;
- amd64 image build and base-image provenance artifact;
- both health endpoints;
- Ingress-prefix correctness;
- bilingual/theme/version UI assertions;
- no normal host exposure of administration listener;
- configurable published `8098` metadata;
- persistent `/data` across restart;
- initial AppArmor executable inventory.

### HAOS acceptance

1. install from repository;
2. confirm clean startup/logs;
3. open Ingress and verify product name + version;
4. verify FR/EN;
5. verify light/dark;
6. verify MCP host port can be changed from Home Assistant Network configuration;
7. restart App and HAOS once and confirm clean recovery.

Lot 0 proves only the HAOS shell/security foundation.

## Lot 1 — authenticated MCP server and generic adapter foundation

Status: **planned**.

### Goal

Turn the shell into a real standalone authenticated MCP server and establish the generic target/adapter foundation, while exposing no target actions until a concrete adapter is implemented.

### Scope

- exact stable official MCP Python SDK v2 pin chosen at implementation time;
- Streamable HTTP `/mcp` endpoint;
- interoperability with current and ACP-era MCP clients on the same endpoint;
- tools-only MCP surface;
- Bridge Bearer issue/replace/revoke lifecycle;
- one-time clear token display;
- verifier-only token persistence with App-local pepper/HMAC key under `/data/private`;
- reject unauthenticated MCP requests;
- reject unsafe browser-Origin access to the MCP endpoint;
- generation-1 common persistence for `settings`, `mcp_credential` and `targets` only;
- generic target adapter-type identifier and adapter registration/dispatch boundary;
- no adapter-specific persistence table before its adapter lot requires one;
- App-local authenticated-encryption key for target secrets;
- encrypted secret storage/redaction utilities;
- generic target repository with stable key, display name, adapter type, enabled state and safe configuration envelope;
- common static target-envelope validation hooks delegated to the selected adapter;
- in-use snapshot/locking foundation;
- bounded global invocation/session accounting foundation;
- Ingress views for MCP access and generic Targets;
- deterministic empty tool inventory until an adapter is implemented;
- no echo/sample tool.

### Anti-goals

No Chromium/browser action, SSH connection, future transport adapter, ACP-specific authorization or per-client permissions.

### CI evidence

- authenticated MCP discovery with empty tool inventory;
- current and earlier compatible MCP client behavior on same endpoint;
- wrong/missing Bearer rejected;
- token replacement invalidates old token;
- clear token not recoverable from API/database/logs;
- encrypted secret utility round-trip without plaintext persistence;
- adapter registration/unknown-adapter fail-closed tests;
- generic target persistence/validation tests;
- Ingress CRUD/persistence shell tests;
- restart with common configuration preserved.

### HAOS acceptance

1. upgrade/install cleanly;
2. issue MCP credential and copy it once;
3. confirm it cannot be redisplayed;
4. connect a compatible MCP client and confirm authenticated empty tool inventory;
5. rotate credential and confirm old token stops working;
6. verify the target administration shell is present but does not pretend an unimplemented adapter exists.

Lot 1 establishes the MCP/security/modular-adapter foundation.

## Lot 2 — interactive Web administration adapter

Status: **planned**.

### Goal

Let a model interactively operate administrator-configured HTTP/HTTPS administration interfaces through bounded MCP browser tools, without requiring a model-specific Browser feature.

### Scope

- register the first concrete adapter type: `web`;
- Web target type with:
  - fixed base HTTP/HTTPS origin;
  - explicit allowed top-level origins, default base origin only;
  - TLS verification default enabled;
  - enabled/disabled state;
  - encrypted authentication material;
  - authentication modes sufficient for common local administration: none, HTTP Basic, configured form login;
  - bounded inactivity and absolute browser-session lifetimes;
- system Chromium + unprivileged browser-driving stack proven inside HAOS base image;
- isolated temporary browser profile/context per session;
- opaque session IDs, target-bound and memory-only;
- deterministic target-scoped MCP Web tool family implementing the behavior defined in the technical design;
- `web_open` equivalent creating/authenticating a session;
- bounded text/accessibility `web_snapshot` equivalent with opaque element references;
- same-target navigation;
- click/fill/select/press/wait actions using current Bridge-issued element refs;
- optional bounded screenshot tool/result path;
- explicit close and deterministic cleanup;
- DOM/page changes invalidate stale element references safely;
- top-level navigation/redirect origin revalidation after every transition;
- no model-supplied CSS/XPath selectors;
- no arbitrary JavaScript;
- no file upload/download;
- no DevTools/remote-debugging MCP surface;
- no arbitrary local filesystem access;
- browser session concurrency bound with immediate busy response;
- no automatic Web action retry;
- Ingress Web target configuration/test/status integrated into the common target UI;
- generated Web tool inventory visible to administrator;
- AppArmor expanded only for the proven Chromium/WebDriver runtime requirements.

### Critical model-path acceptance

The normative path is **text/tool calling only**:

`model -> MCP web_snapshot -> textual/structured page state -> model -> MCP action tool -> ...`

A non-vision tool-calling model must be able to use a deterministic fixture end to end. Screenshot/vision is supplementary only.

### Security gate

Lot 2 is **not accepted** if Chromium requires making the App privileged, granting broad host filesystem/device access or weakening AppArmor beyond a defensible browser-runtime boundary.

If the selected browser-driving stack cannot meet this under HAOS, change the technical browser-driving implementation and retest. Do not weaken the product security boundary simply to preserve a library choice.

### CI evidence

Use a deterministic local web administration fixture proving:

- open + configured login;
- secrets never exposed to MCP/model/logs;
- bounded textual snapshot useful to a non-vision client;
- stable element refs for current page generation;
- click/fill/select/press/wait flow;
- stale ref rejection after navigation/DOM change;
- allowed relative navigation;
- external-origin/top-level redirect escape rejected;
- no arbitrary selector/JS/path inputs;
- session isolation;
- inactivity/absolute expiry;
- explicit close cleanup;
- crash/shutdown cleanup;
- restart invalidates old session IDs without replay;
- optional screenshot path bounded;
- AppArmor executable/process inventory includes only required browser runtime;
- common MCP/auth/target tests remain unchanged and green.

### HAOS acceptance

Configure one harmless local administration interface fixture and verify:

1. target saves/tests cleanly;
2. MCP client discovers only that target's generated Web tool family;
3. open session and retrieve readable text snapshot;
4. use snapshot element refs to navigate/click/fill a harmless test setting;
5. confirm model/client never receives stored login credentials;
6. attempt an external-origin navigation and confirm rejection;
7. close session and confirm cleanup/state disappears;
8. restart App/HAOS and confirm no browser process/session is resurrected.

Lot 2 proves the core real-world Web administration use case.

## Lot 3 — bounded SSH adapter

Status: **planned**.

### Goal

Add SSH as a second independent adapter and expose administrator-defined SSH operations as ordinary bounded MCP tools without providing an unrestricted shell.

### Scope

- register adapter type `ssh` without changing the Web adapter contract;
- SSH target:
  - fixed host/IP, port and username;
  - encrypted password/private-key/passphrase credential support where safe;
  - mandatory pinned/trusted host-key material;
  - enabled/disabled state;
- add SSH-owned persistence for bounded SSH capability definitions;
- explicit SSH target connectivity/auth/host-key test without arbitrary remote command;
- bounded SSH capability definitions with:
  - stable MCP tool name;
  - title/description;
  - strict input object schema;
  - fixed command/executable head;
  - ordered literal/input argument template;
  - timeout/output limits;
  - enabled/disabled state;
- POSIX-safe argument construction;
- no caller whole-command string;
- no PTY, arbitrary env map or unrestricted stdin in initial release;
- bounded stdout/stderr/exit-status result;
- no automatic command retry;
- Ingress SSH target/capability CRUD/test/status integrated with the common administration shell;
- target/capability in-use mutation protection;
- AppArmor updated only for actual SSH library/runtime needs.

### Anti-goals

No `ssh_exec(command: string)`, no terminal, no remote account management, no sudo policy editor and no appliance-specific command presets in core.

### CI evidence

Local deterministic SSH fixture proves:

- host-key pinning success/failure;
- password/private-key auth paths implemented by the chosen baseline;
- secret non-disclosure;
- fixed command execution;
- variable argument mapping;
- shell/injection probes remain data rather than syntax;
- caller cannot replace host/user/whole command;
- timeout/output bounds;
- no retry after ambiguous failure;
- disabled/invalid SSH capabilities absent from MCP tool discovery;
- Web adapter and common MCP/auth tests remain unchanged and green.

### HAOS acceptance

Against a deliberately restricted test SSH account:

1. configure and validate target;
2. create one harmless fixed command capability;
3. discover/call it from a generic MCP client;
4. verify arguments cannot escape the command template;
5. verify wrong host-key/config fails closed;
6. verify credentials never appear in UI/log/MCP result;
7. disable capability and confirm disappearance from discovery.

Lot 3 proves that a second adapter can be added without turning the core into adapter-specific logic.

## Lot 4 — hardening, interoperability, documentation and production cutoff

Status: **planned**.

### Goal

Close the first production-ready release after the initial Web and SSH adapters are real and accepted on HAOS.

### Scope

- full threat-model review for common Bridge core, Web, SSH, MCP endpoint, secrets and HAOS runtime;
- bounded hard limits finalized from test evidence;
- graceful shutdown/drain and adapter cleanup verification;
- concurrency/busy behavior under load;
- malformed/oversized MCP argument/result cases;
- browser session leak/stale-handle tests;
- browser process crash tests;
- SSH ambiguous-failure/no-retry tests;
- credential rotation while targets active/inactive;
- prove adapter isolation: Web-specific failure/change does not break SSH/common core and vice versa;
- Ingress responsive/polished bilingual UI consistency with ACP;
- final dedicated logo/icon if initial assets were temporary;
- complete `README.md`, `README.fr.md` and HAOS `DOCS.md`/equivalent bilingual documentation;
- connection examples for generic MCP client, ACP and Execution Plane without private coupling;
- real Agent Control Plane connector discovery of Bridge Web/SSH tools through standard MCP only;
- real generic MCP client interoperability;
- amd64/aarch64 build validation where repository infrastructure permits;
- AppArmor real HAOS startup/use/shutdown/restart acceptance;
- declare production-data preservation cutoff.

### Release invariants

Before production cutoff:

- Bridge must run usefully with no ACP/Execution Plane installed;
- common MCP/auth/target code must not structurally depend on Web or SSH internals;
- Web administration must work with an ordinary tool-calling non-vision model path;
- ACP sees Bridge as an ordinary MCP server;
- no model/client can escape the administrator-configured target envelope;
- no target credential is disclosed;
- adapter resources clean up deterministically;
- no automatic target-operation retry/replay exists;
- no permanent invocation/browser history has appeared;
- no unplanned future adapter has been slipped into the release.

### HAOS acceptance

Perform final real-install acceptance covering:

1. clean install/start/Ingress/UI/theme/language/version;
2. MCP credential issue and rotation;
3. Web target end-to-end interactive administration fixture;
4. SSH bounded command fixture;
5. generic MCP client discovery/calls;
6. ACP connector discovery/calls using ordinary MCP only;
7. restart during/after browser session and verify cleanup/no replay;
8. persistence of common target and adapter-owned configuration;
9. AppArmor denial-free normal operation with no unjustified permissions;
10. backup/restore or equivalent persistence check required by the final HAOS packaging policy.

After this lot is accepted, supported Bridge target, credential and adapter-owned configuration is **production data**. Future schema changes require explicit deterministic tested upgrades; routine data removal/clean reinstall is no longer an acceptable upgrade strategy.

## Future adapter extensions — intentionally outside this plan

The first release stops at Web + SSH.

A future need such as FTP/SFTP, direct API access or another technical transport does **not** get implemented speculatively now. When such a need becomes real, it receives its own bounded adapter design/implementation lot covering:

- target configuration and credentials;
- MCP tool contract;
- transport-specific security envelope;
- resource/time/output limits;
- AppArmor/runtime additions if any;
- CI fixtures;
- documentation FR/EN;
- real HAOS acceptance.

The acceptance test for the architecture is that such a future adapter can be added without redesigning common MCP authentication, unrelated adapters or suite integrations.

## Delivery discipline

For each lot, the assistant determines the next bounded scope from this plan and gives Codex a precise implementation instruction.

After Codex pushes:

1. independently inspect actual diff/code/tests;
2. independently inspect CI evidence;
3. request only focused micro-patches for real defects/drift;
4. re-review patches and CI;
5. deploy only conformant code to HAOS;
6. run the lot's HAOS acceptance one practical step at a time;
7. mark the lot accepted only after real HAOS success.

No lot advances merely because Codex reports completion.
