# MCP Capability Bridge — Threat Model

Status: **normative threat model — audited and accepted for the 1.0.0 production cutoff**.

## 1. Assets

Protected assets include MCP namespace credentials, target passwords/private keys, pinned SSH host keys, browser cookies and temporary profiles, target configuration, namespace publication boundaries, HAOS private state and the integrity of target operations.

Arbitrary target page content and SSH output may be sensitive even when the Bridge cannot classify it in advance.

## 2. Trust boundaries

The main boundaries are:

1. Home Assistant Ingress administrator to administration API;
2. external MCP client to authenticated namespace;
3. namespace/tool call to Bridge registry and adapter;
4. Bridge adapter to configured target;
5. browser process/driver and temporary profile to Bridge runtime;
6. Bridge runtime to SQLite and `/data/private`;
7. Bridge to optional ACP and AEP through ordinary MCP only.

ACP is not trusted to repair an intrinsically unlimited Bridge capability. The Bridge is independently responsible for its maximum technical envelope.

## 3. Threat actors

- unauthenticated network client;
- holder of one valid namespace credential attempting cross-namespace access;
- model or MCP client supplying hostile tool arguments;
- compromised or malicious Web target content;
- hostile SSH output or remote shell behavior;
- administrator configuration mistake;
- lost MCP response causing an unsafe retry;
- crashed browser/driver or App process;
- future dependency update adding executables or changing protocol behavior.

The Ingress administrator is trusted to deliberately grant target and account authority, but the UI must make high-impact choices explicit.

## 4. Namespace threats

| Threat | Required control | Evidence |
| --- | --- | --- |
| Credential guessing | 256-bit random tokens, fast HMAC verifier, constant-time comparison | unit and API tests |
| Token disclosure | one-time display, no clear persistence/logging/API recovery | database/log/UI tests |
| Cross-namespace discovery | namespace-filtered registry query | two-client contract test |
| Cross-namespace session hijack | handle bound to namespace and credential generation | real Web session test |
| Old token remains usable | transactional rotation and immediate invalidation | API/MCP test |
| Rotated/revoked client keeps browser authority | cancel all owned sessions/operations | concurrency test |
| Archived namespace reactivates | archive only after revoke; no restore access | lifecycle test |
| Excess calls create an implicit queue | fail-fast global, namespace, adapter and target limits | concurrency tests |

Namespace publication is technical isolation, not ACP-style business authorization.

## 5. Target/configuration threats

| Threat | Required control |
| --- | --- |
| Caller replaces target or credential | target and secrets absent from tool arguments |
| Stale tool remains callable | dispatch-time publication/target/schema revalidation |
| Mutation races with execution | one authoritative runtime, active-use leases and immutable snapshots |
| Secret rotation partially applies | transaction plus explicit adapter invalidation |
| Unknown adapter executes | static registry and fail-closed type lookup |
| Schema accepted by Bridge but rejected by ACP/provider | shared admitted subset and real ACP/AEP contract tests |

## 6. Web threats

| Threat | Required control |
| --- | --- |
| Model exceeds intended account rights | dedicated least-privilege target account; UI states actual authority boundary |
| Navigation escapes target | categorized origin/address allowlists and validation after every redirect/navigation |
| DNS rebinding reaches another local service | confirmed address set; resolution change fails closed |
| Hidden iframe/popup escape | one top-level context; unapproved frames/windows blocked |
| WebSocket/subresource exfiltration | categorized resource/WebSocket origin guard |
| `file:`/`javascript:`/downloads access host data | prohibited schemes, downloads/uploads and filesystem access |
| Credential exfiltration to another origin | inject only in configured auth flow/origin; block cross-origin submission |
| Stale reference clicks different element | generation-bound fingerprint, immediate revalidation, invalidate after every action |
| Concurrent calls corrupt session | one lock and one in-flight operation per session |
| Session handle stolen by another namespace | namespace/generation binding and random handle |
| Browser profile survives | dedicated temporary root, no `/data`, cleanup on close/startup |
| Screenshot exposes unknown secrets | screenshot absent from initial contract |
| Snapshot exposes passwords/cookies | accessibility-only bounded representation; sensitive fields omitted; known-secret redaction |
| Malicious page exhausts resources | browser/session/process/memory/time/output limits and forced cleanup |

Visible page content may still contain unknown sensitive operational data. This residual risk is documented rather than hidden behind an impossible universal-redaction promise.

## 7. SSH threats

| Threat | Required control |
| --- | --- |
| Arbitrary command injection | no command-string argument; quoted token template only |
| Shell metacharacters become syntax | POSIX single-token encoding and control-character rejection |
| Host impersonation | explicit key enrollment and exact pin verification |
| Silent host-key rotation | fail closed and require administrator confirmation |
| Persistent shell state | fresh connection, no PTY/multiplexing/agent forwarding |
| Output/resource exhaustion | streaming byte/time limits and deterministic close |
| Automatic duplicate side effect | no retry; effect-possible outcome after exec acceptance |
| Credential leak in errors/output | bounded safe errors and exact known-secret redaction |

Residual limitation: SSH sends a remote command string interpreted by the target's declared POSIX shell. Version one does not claim universal non-shell `argv` execution.

## 8. Ambiguous outcomes

For effect-capable calls, the target may complete an action while the MCP response is lost. The Bridge cannot promise exactly-once execution without durable invocation state, which is intentionally outside scope.

Controls:

- no automatic adapter retry;
- `effect_possible` propagated through bounded errors;
- optional runtime-only duplicate request cache;
- cancellation/shutdown preserve ambiguity;
- client documentation prohibits automatic retry after effect may be possible;
- HAOS tests deliberately lose responses after target acceptance.

## 9. Persistence and logging threats

SQLite and logs must never contain clear namespace tokens, target secrets,
browser storage, MCP arguments, snapshots, SSH output or upstream exception
payloads. The persistent Activity journal is capped at 500 rows and admits only
timestamp, event/status, safe source/client/tool/adapter identifiers and
duration; it contains no request or result payload.

Private keys use separate atomic `0600` files. Encrypted target payloads use authenticated encryption. Normal logs use IDs, counters, durations and safe enumerated codes only.

Supervisor logging may outlive the App, so “not a database table” is not sufficient: sensitive payloads must never reach logging calls.

## 10. HAOS/AppArmor threats

Every installed executable reachable by the runtime must be inventoried and either deliberately allowed or absent. CI compares image inventory against AppArmor rules and Unix execute bits.

Browser dependencies do not justify privileged mode, host networking, broad `/dev`, broad `/proc`, Home Assistant data access or global Python/site-packages execution rules. Temporary profile and shared-memory paths are explicit and bounded.

## 11. ACP/AEP integration threats

| Threat | Required control |
| --- | --- |
| ACP discovery treated as authorization by Bridge | Bridge still enforces namespace publication and technical envelope |
| Bridge knows ACP jobs/policies | ordinary MCP only; no ACP-specific state |
| ACP task gains tools after configuration change | fingerprints and task fail-closed behavior |
| AEP bypasses ACP using another namespace | credentials remain separately administered; no implicit suite trust |
| Result content breaks AEP/provider | bounded structured/text contract tested end to end |
| Image/screenshot path falsely assumed supported | no screenshot in initial Web contract |

## 12. Acceptance rule

A lot is not accepted when only unit tests pass. Browser, SSH, process topology, listener isolation, cleanup, credential rotation and AppArmor require real HAOS evidence. Any new adapter requires its own threat-model section before implementation.

The Lot 4 audit also requires malformed and oversized MCP requests, fail-fast
capacity, cancellation/shutdown, mutation races, repeated SSH/Web cleanup,
supported image architectures, cold backup/restore and no-replay restart
evidence before the production cutoff.
