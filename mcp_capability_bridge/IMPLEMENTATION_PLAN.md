# MCP Capability Bridge — Implementation Plan

Status: **authoritative sequence — Lots 0 through 3A accepted on HAOS**.

This plan derives from `PROJECT_BRIEF.md`, `TECHNICAL_DESIGN.md`, `THREAT_MODEL.md` and `ARCHITECTURE_CHARTER.md`.

For every lot:

`planned -> implemented -> independently reviewed -> CI conformant -> deployed on HAOS -> real acceptance tested -> accepted`

Only one bounded lot is implemented at a time. Findings from review or HAOS return to a focused corrective patch; they do not silently expand the next lot.

## Global invariants

Every lot preserves:

- independent generic MCP server with no required ACP/AEP dependency;
- ordinary MCP-only suite integration;
- isolated MCP client namespaces from the first authenticated release;
- adapter-oriented statically packaged core, with no runtime executable plugins;
- SSH and Web as initial adapters, not hard-coded product limits;
- no models, tasks, jobs, schedules, reports or business policy;
- target and namespace secrets owned only by the Bridge;
- no unrestricted SSH command string;
- Web authority equal to the configured target account and explicit network envelope;
- no automatic operation retry or durable invocation queue/history;
- disposable browser sessions and fresh SSH connections;
- one authoritative runtime for 8098/8099 state;
- unprivileged HAOS and evidence-based AppArmor;
- ACP/AEP visual conventions for the Ingress UI;
- committed `icon.png` and `logo.png` unchanged unless explicitly re-approved;
- FR/EN, light/dark, responsive UI and stable scrollbar geometry;
- no production-data cutoff before all adapters and upgrades are accepted on HAOS.

## Lot 0 — HAOS shell and shared suite UI

Status: **accepted on HAOS — 2026-08-21**.

### Goal

Create the executable App shell and prove the single-runtime/two-surface topology before persistence, MCP authentication or adapters exist.

### Scope

- HAOS metadata and initial synchronized version source;
- preserve/package authoritative icon and logo;
- one unprivileged application runtime starting separate administration and public ASGI applications;
- Ingress-only 8099 and public 8098 health endpoints;
- configurable host mapping for 8098;
- database generation-one initialization plumbing without product tables beyond metadata;
- graceful shutdown foundation;
- first observed AppArmor executable inventory;
- ACP/AEP-style header, navigation, cards, `pagehead split`, right drawer foundation, colors and spacing;
- stable `scrollbar-gutter` and responsive mobile layout;
- FR/EN and light/dark controls;
- Overview showing only real readiness;
- CI workflow and basic bilingual installation documentation.

### Anti-goals

No MCP endpoint, credentials, namespaces, targets, adapter registry, SSH or browser packages.

### CI evidence

- metadata/version/assets synchronized;
- Python/shell syntax and unit tests;
- image build/provenance;
- one runtime owns both listener servers;
- strict route/listener isolation;
- Ingress-prefix-safe assets;
- shared UI conventions, drawer focus behavior and no horizontal shift;
- restart and shutdown;
- AppArmor executable inventory.

### HAOS acceptance

Install, start, open Ingress, verify product/version/icon, menu, top-right actions, drawer behavior, FR/EN, light/dark, mobile/desktop scrollbar stability, configurable 8098 mapping and clean restart.

Accepted on real HAOS with version 0.1.0: generation-one initialization, the shared PID for both listeners, all navigation views, drawer behavior, FR/EN, light/dark, mobile layout, stable horizontal geometry, stop and restart were verified without startup error or AppArmor denial.

## Lot 1 — namespaces, authenticated MCP and adapter core

Status: **accepted on HAOS — 2026-08-21**.

### Goal

Deliver the secure standalone MCP core, multi-client namespace isolation, protected configuration storage and empty adapter registry.

### Scope

- exact MCP SDK pin compatible with current ACP code;
- authenticated Streamable HTTP `/mcp`;
- tools-only surface with empty inventory initially;
- namespace create, one-time credential display, rotate, revoke and revoke-then-archive lifecycle;
- 256-bit opaque credentials, indexed HMAC verifier and constant-time comparison;
- encrypted target-secret utility with a separate atomic key;
- generic targets and static adapter registry interfaces;
- namespace-to-capability publication model;
- global/per-namespace concurrency foundation;
- shared operation/session counters visible to administration;
- MCP Clients, Targets and MCP Access views using shared drawers/filters;
- no fake or echo production tool.

### Required behavior

- different namespace credentials discover only their own publications;
- an unknown/revoked/archived namespace cannot initialize MCP;
- rotation invalidates the old token immediately;
- administration and MCP observe the same runtime state;
- public APIs never expose admin routes or clear secrets.

### CI evidence

- credential non-disclosure and restart persistence;
- cross-namespace discovery/call denial with adapter test doubles;
- publication revision and `tools/list_changed` behavior;
- encrypted target-secret persistence;
- active-use mutation tests across both listener applications;
- current ACP connects as an ordinary client, validates the real MCP contract and discovers the expected empty/published test-double inventory;
- tool names and schemas satisfy ACP limits/admitted JSON Schema subset;
- no clear token/secret in database, logs, responses or UI after acknowledgement.

### HAOS acceptance

Create two namespaces, issue/rotate credentials, connect two generic MCP clients plus ACP, prove isolated inventories, revoke one without affecting the other, archive it through the filter and restart with only configuration preserved.

Accepted on real HAOS with version 0.2.0: Ingress, FR/EN, light/dark, empty target/access states, two isolated MCP clients, ACP empty-inventory discovery, one-time credentials, rotation invalidation, revocation, revoke-before-archive filtering and restart persistence were verified. Shutdown/startup and post-restart `ListToolsRequest` completed without secret disclosure, application error or AppArmor denial.

## Lot 2 — bounded SSH adapter

Status: **accepted on HAOS — 2026-08-21**.

### Goal

Prove the adapter architecture with independently configured, precisely bounded SSH capabilities.

### Scope

- SSH target CRUD and encrypted password/private-key authentication;
- two-step host-key scan, fingerprint display, explicit confirmation and rotation;
- explicit POSIX remote-command contract;
- SSH capability CRUD with stable tool key, absolute executable and quoted token template;
- scalar typed parameters and strict ACP-compatible schemas;
- timeout and separate stdout/stderr bounds;
- fresh connection per call, no PTY, forwarding, agent, environment map, stdin or multiplexing;
- publication to one or more namespaces;
- target/capability in-use mutation protection;
- safe effect-possible errors and no retry;
- SSH views/drawers matching suite UI.

### CI evidence

Use a deterministic local SSH fixture to prove:

- exact host-key enrollment and changed-key refusal;
- password/key secret protection;
- one new connection per call and deterministic close on success/failure/timeout/cancellation;
- token-template injection remains one POSIX argument, including hostile metacharacters/newlines/control cases;
- no caller-controlled command head, shell operator, PTY or forwarding;
- output truncation without unbounded buffering;
- no arguments/stdout/stderr/secret persistence or logging;
- ambiguous post-exec response loss returns `effect_possible: true` and is not replayed;
- namespace publication isolation;
- current ACP discovers/calls the real SSH tool and AEP receives the bounded result through ACP without special handling.

### HAOS acceptance

Enroll a restricted test host key, configure a harmless read capability, publish it to one namespace, call twice through a generic client and once through ACP/AEP, prove distinct connections, hidden credentials, bounded output, clean disable and denial-free AppArmor operation.

Accepted on real HAOS with version 0.3.0: a restricted SSH target and capability were created and invoked successfully both directly and through ACP/AEP; a second invocation used the fresh-connection path; two MCP client namespaces remained isolated; disable/re-enable and target `In use` protection behaved correctly; configuration survived restart; and logs remained free of application errors, credential disclosure and AppArmor denials.

## Lot 3A — browser runtime and confinement gate

Status: **accepted on HAOS — 2026-08-21**.

### Goal

Package and confine a real browser safely before exposing any browser MCP tool.

### Scope

- evidence-driven selection of unprivileged browser/driver stack;
- exact installed executable/helper/library inventory;
- dedicated non-persistent temporary profile root and bounded shared memory;
- process-tree supervision and cleanup;
- internal network/origin request guard foundation;
- browser global/per-namespace/per-target resource limits;
- startup cleanup of stale validated temporary directories;
- Web target static configuration UI without enabled MCP tools.

### CI evidence

- browser/driver versions reproducible on supported architectures;
- every executable has Unix execute permission and targeted AppArmor coverage;
- future executable additions fail CI until reviewed;
- local fixture launch/terminate/crash/timeout leaves no process or reusable profile;
- no browser write under `/data` except encrypted target configuration;
- unapproved scheme/origin/address/frame/popup/WebSocket/download requests blocked;
- one browser failure does not make the App restart-loop or affect SSH.

### HAOS acceptance

Configure a harmless local Web fixture, run explicit connectivity/browser tests, inspect processes/temp storage/AppArmor, crash the browser and restart the App, confirming no restored session or broad permission requirement.

Accepted on real HAOS with version 0.4.4: startup, desktop/mobile UI, Web target creation and restart persistence, two consecutive browser tests, forbidden URL/scheme rejection, cross-origin redirect rejection, absence of premature Web MCP tools, SSH non-regression and recovery after an unreachable target were verified. Chromium required only the focused AppArmor corrections delivered in 0.4.3 and 0.4.4; final logs contained no application error or AppArmor denial.

## Micro-lot UX — generated technical keys

Status: **accepted on HAOS — 2026-08-21**.

### Goal

Remove unnecessary technical-key entry from ordinary administration flows while preserving stable public MCP identifiers and every existing reference.

### Scope

- inventory every user-visible technical key for MCP clients, targets, capabilities and future adapter entities;
- classify keys as internal identifiers or intentionally user-controlled public contract names;
- derive eligible keys from the display name in the backend at creation time;
- normalize deterministically and resolve collisions without crossing namespace boundaries;
- keep generated keys immutable when a display name is edited;
- hide generated keys from primary forms, with optional read-only display only where operationally useful;
- preserve all existing API/MCP contracts, stored references, namespace isolation and audit semantics.

### Anti-goals

- no key regeneration on rename;
- no silent mutation of existing keys;
- no migration or historical compatibility work unless separately justified;
- no adapter, browser, SSH, ACP or AEP behavior change.

### CI evidence

- deterministic normalization covers accents, whitespace, punctuation, empty output and length bounds;
- collisions produce distinct stable keys under the correct uniqueness scope;
- rename leaves the key and all publications/references unchanged;
- creation through the UI and administration API uses the same backend generation rule;
- fields that must remain explicit for a public contract are documented and tested as such.

Accepted on real HAOS with version 0.4.5: technical-key fields were absent from the client, SSH target, Web target and SSH capability creation flows; duplicate display names produced distinct coexisting records; and renaming preserved the generated technical key and functional references.

## Lot 3B — isolated read-only Web sessions

Status: **implemented; awaiting HAOS acceptance**.

### Goal

Expose the non-vision read path and prove namespace/session/reference isolation before effect-capable actions exist.

### Scope

- Web authentication modes none, Basic and bounded configured form login;
- target-scoped `open`, `snapshot`, bounded read-only `wait` and `close` tools;
- random namespace/generation-bound handles;
- one lock per session;
- textual/accessibility snapshots with total/node/depth/field bounds;
- password/hidden/cookie/storage/script/style/raw-HTML exclusion;
- known-secret redaction;
- inactivity/absolute expiry and unified cleanup;
- no screenshot.

### CI evidence

- two namespaces on the same target cannot use each other's handles;
- rotation/revocation closes only the owning namespace's sessions;
- two consecutive sessions never share cookies/storage/history/profile state;
- login secrets never enter schemas/results/logs;
- stale generation and concurrent calls fail closed;
- browser crash, timeout, close, App shutdown and restart clean everything;
- text path works through generic MCP, current ACP and AEP without vision support.

### HAOS acceptance

Use read-only credentials against a fixture, open/snapshot/close directly and through ACP/AEP, verify clean second session, namespace isolation, expiry, rotation cleanup and no persistent browser state.

## Lot 3C — interactive Web actions

Status: **planned**.

### Goal

Add effect-capable interaction while explicitly preserving the configured Web account as the real authority boundary.

### Scope

- target-scoped relative navigation, click, fill, select, press and bounded wait;
- categorized navigation/auth/resource/WebSocket origin policy;
- confirmed address set and DNS-change failure;
- one top-level context, no popups/downloads/uploads/filesystem access;
- generation-bound element fingerprints and immediate pre-action revalidation;
- invalidate all references after every attempted action;
- no model-driven password-field filling;
- `effect_possible` transitions and no retry;
- prominent least-privilege account/TLS warnings in UI and docs.

### CI evidence

- read-only target account cannot perform fixture admin operations;
- admin target account can perform only operations the fixture exposes to it;
- Bridge/ACP do not claim finer click authorization;
- origin, redirect, iframe, popup, WebSocket, scheme and DNS-rebinding escapes fail closed;
- semantic element replacement between snapshot/action produces `stale_reference`;
- simultaneous actions serialize;
- lost response after a fixture side effect is not replayed and reports ambiguity;
- no unknown URL, selector, script, credential, upload or download surface exists.

### HAOS acceptance

Test one dedicated read-only account and one deliberately privileged fixture account, demonstrate the difference in actual target authority, verify every confinement rule, then repeat through ACP/AEP with only the chosen Web tools authorized.

## Lot 4 — hardening, documentation and production cutoff

Status: **planned**.

### Goal

Close the first production-ready release only after SSH and Web have independent real HAOS acceptance.

### Scope

- complete threat-model audit against actual code;
- malformed/oversized MCP and concurrency stress cases;
- cancellation/shutdown/lost-response matrix;
- credential/target mutation races;
- long repeated Web cleanup and SSH isolation runs;
- final AppArmor and supported-architecture image evidence;
- polished bilingual Ingress and complete README/README.fr/HAOS documentation;
- standalone examples and ordinary ACP/AEP integration examples;
- backup/restore and deterministic upgrade strategy;
- production-data preservation cutoff declaration.

### Release invariants

- multiple namespaces remain isolated;
- Bridge works independently;
- ACP sees only its namespace publications and further narrows them per task;
- AEP receives/calls tools only through existing MCP boundaries;
- Web authority is never overstated beyond the target account;
- SSH has no generic command primitive;
- no runtime sessions/output/history survive;
- no automatic replay exists;
- UI is visibly and behaviorally consistent with ACP/AEP;
- no unjustified HAOS/AppArmor privilege exists.

### HAOS acceptance

Perform clean install, upgrade, backup/restore, UI, multi-client auth, SSH, read-only Web, privileged Web, generic client, ACP/AEP, restart-during-operation, cleanup, rotation/revocation, AppArmor and resource-bound tests. Only then mark the plan accepted and make future schema migrations mandatory.

## Delivery discipline

Each future Codex instruction is derived from one lot and repeats its invariants, anti-goals, tests and terminal acceptance boundary. Documentation status is updated only after independent review, green CI and real HAOS evidence.
