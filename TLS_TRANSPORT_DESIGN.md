# ACP, AEP and MCP Capability Bridge — Public Transport Security Design

Status: **decisions validated; authoritative input for implementation**.

This document records the shared transport-security design for Agent Control
Plane (ACP), Agent Execution Plane (AEP), and MCP Capability Bridge (Bridge).
It covers public application surfaces and outbound partner connections. Home
Assistant Ingress administration remains mandatory and is explicitly outside
the TLS scope of this design: HAOS owns the user-facing security of Ingress.

The design is intended for public applications deployed in different network
topologies. No assumption about one administrator's private network is a product
requirement. HTTP remains supported where interoperability or deployment
topology requires it, and its consequences must always be visible.

## 1. Core decisions

1. Every public surface independently supports either HTTP or HTTPS.
2. HTTP is a supported administrator choice, not a hidden compatibility mode.
3. Every active HTTP surface or outbound HTTP destination is clearly reported
   as unencrypted in English logs and in the bilingual administration UI.
4. An HTTPS server surface uses one of two certificate sources:
   - a persistent application-generated certificate; or
   - an administrator-provided external certificate and private key.
5. An outbound HTTPS connection authenticates its peer using either:
   - normal system trust validation when no fingerprint is configured; or
   - an exact pinned SHA-256 certificate fingerprint when configured.
6. Disabling normal certificate validation without an exact fingerprint is
   forbidden.
7. Peer certificate verification, including fingerprint comparison, completes
   before any Bearer credential, event, job, tool argument, or other sensitive
   application payload is transmitted.
8. HTTP and HTTPS redirects are never followed on authenticated application or
   MCP connections.
9. Transport or certificate changes take effect after an explicit application
   restart. Hot TLS reload is not required.
10. Temporary interruption during certificate replacement is accepted. Dual
    current/future certificate fingerprints and staged rotation are not part of
    this design.
11. Fresh-install transport defaults are:
    - ACP Event Intake API: HTTP;
    - ACP MCP Worker Endpoint: HTTPS with an application-generated certificate;
    - AEP Standalone Execution API: HTTPS with an application-generated
      certificate;
    - Bridge MCP endpoint: HTTPS with an application-generated certificate.
    These are defaults, not restrictions. The administrator may select HTTP or
    HTTPS independently for every public surface. ACP Event Intake may later be
    changed to HTTPS after the administrator verifies the TLS capabilities and
    trust configuration of Home Assistant or another event producer.

## 2. Public surfaces

### 2.1 ACP must split its two public responsibilities

The existing ACP public listener combines two unrelated boundaries whose
clients can have different TLS capabilities. They must become disjoint ASGI
surfaces and distinct publishable container ports:

| Internal port | Surface | Purpose |
| --- | --- | --- |
| `8098/tcp` | Event Intake API | Authenticated event creation and any strictly event-intake public routes |
| `8100/tcp` | MCP Worker Endpoint | MCP job claim, lease, completion, failure, report delivery, and other worker MCP operations |
| `8099/tcp` | Ingress administration | Mandatory HAOS Ingress; unchanged and outside this TLS design |

The Event Intake port must not expose `/mcp`. The MCP port must not expose
`/api/v1/events`. Cross-surface requests return `404`. Each public surface may be
configured as HTTP or HTTPS independently.

Both HTTPS surfaces use the same ACP server certificate and private key. ACP
does not manage separate event and MCP certificates.

The two public ports must be independently publishable in the HAOS App network
configuration. Their English port descriptions must state their exact roles,
for example:

```yaml
ports:
  8098/tcp: null
  8100/tcp: null

ports_description:
  8098/tcp: "Authenticated event intake API"
  8100/tcp: "Authenticated MCP worker endpoint"
```

### 2.2 AEP keeps one public surface

AEP's standalone API is one coherent execution lifecycle: submit an execution,
inspect it, retrieve its report, and acknowledge the result. It keeps one
public port, configurable globally as HTTP or HTTPS. The ACP worker boundary is
an outbound connection and does not require a second AEP server surface.

### 2.3 Bridge keeps one public surface

Bridge keeps one public MCP surface, configurable globally as HTTP or HTTPS.
Its Ingress administration and public MCP ASGI applications remain disjoint.

Bridge deliberately owns both Uvicorn servers in one process and event loop so
they can share process-local operation limits, tasks, browser sessions, locks,
adapter state, and administration telemetry. That architecture remains. Public
TLS failure must no longer terminate or prevent the Ingress administration
server: the public server is omitted or remains unavailable while the shared
runtime and administration continue running.

## 3. Public transport configuration

Configuration naming may follow each App's established prefix, but the product
model must be identical.

For AEP and Bridge:

```yaml
public_transport: https  # http | https
certificate_source: self_generated  # self_generated | external; used by HTTPS
certfile: ""
keyfile: ""
```

For ACP:

```yaml
events_transport: http  # http | https
mcp_transport: https    # http | https
certificate_source: self_generated
certfile: ""
keyfile: ""
```

These examples are also the required fresh-install defaults. They make TLS the
normal transport for MCP and standalone execution while retaining immediate
compatibility for event producers. Existing or external HTTP-only integrations
remain supported through explicit administrator configuration.

Exact option names will be finalized consistently during implementation.
Certificate settings are irrelevant when no public surface uses HTTPS. Invalid
or contradictory combinations fail closed for the affected HTTPS surface and
are explained in the administration UI.

HTTP does not imply that an installation is necessarily exposed or unsafe; the
application does not know the surrounding network boundary. Warnings must state
the factual consequence: this application is not encrypting the traffic.

## 4. Application-generated server certificates

Application-generated certificates are the expected convenient default for
private ACP/AEP/Bridge relationships. Each App owns at most one generated
server certificate.

The baseline generation profile is:

- RSA 2048-bit private key for broad client compatibility;
- SHA-256 signature;
- random certificate serial number;
- Basic Constraints `CA:FALSE`;
- Extended Key Usage `serverAuth`;
- appropriate RSA key usage;
- validity of five years;
- a small backward offset on `notBefore` to tolerate clock skew;
- persistent storage below `/data/private/tls`;
- private directory mode `0700` and private key mode `0600`;
- ownership by the unprivileged application runtime user;
- inclusion in normal App data backups;
- no regeneration on restart, upgrade, hostname change, or address change.

The generated certificate is trusted by exact fingerprint, so it does not need
to predict every HAOS hostname, mapped address, or IP in its SAN. Clients that
require conventional hostname validation must use an externally provided
certificate appropriate for that deployment.

Generation occurs only when no generated identity exists or when an
administrator explicitly confirms regeneration through Ingress administration.
Regeneration replaces both the key and certificate immediately. Temporary
partner disconnection is expected until fingerprints are updated.

The confirmation text must state, in both UI languages, that the SHA-256
fingerprint will change and every pinned partner will refuse the connection
until updated.

## 5. Administrator-provided server certificates

An external certificate and key are selected by relative filenames resolved
only within the read-only `/ssl` mount. Absolute paths, traversal, and resolution
outside `/ssl` are forbidden. Both values must be supplied together.

Before starting an HTTPS surface, the App validates at least:

- both files exist and are readable;
- both contain supported PEM material;
- the private key matches the leaf certificate;
- the certificate is currently valid;
- the certificate is not a CA certificate;
- a TLS server context can be created from the pair.

The administrator is responsible for making an external certificate trusted by
each intended client, including its chain, SAN values, DNS, and renewal. The App
does not automatically issue, import, or distribute a private CA in this design.

The UI regeneration action is available only for application-generated
certificates. For an external certificate, the UI instructs the administrator
to replace the configured files and restart the App.

## 6. Certificate failure containment

HAOS Ingress administration must start and remain usable when any public TLS
certificate is missing, malformed, mismatched, not yet valid, or expired.

The Apps must prevalidate certificate dates. Loading a certificate into OpenSSL
is insufficient because a TLS server can start with an expired certificate and
leave rejection to clients.

Failure affects only public HTTPS listeners that require the invalid shared
certificate:

- ACP with Event HTTP and MCP HTTPS keeps Event and Ingress available while MCP
  remains unavailable;
- ACP with both public surfaces HTTPS keeps Ingress available while both public
  surfaces remain unavailable;
- AEP keeps Ingress available while its HTTPS standalone API remains
  unavailable;
- Bridge keeps its shared runtime and Ingress administration available while
  its HTTPS MCP listener remains unavailable.

English logs and the bilingual UI must state the exact certificate failure, the
affected surface or surfaces, and the corrective action. Transport changes and
certificate correction are applied by restarting the App.

## 7. Fingerprints and peer authentication

The certificate SHA-256 fingerprint is public metadata, not a secret. Every App
must display it in its bilingual Ingress UI and may emit it in English logs.

For both generated and external certificates, show:

- SHA-256 fingerprint in a copyable canonical colon-separated form;
- certificate source;
- subject;
- issuer;
- validity dates;
- current validity status.

Input fingerprint normalization follows the existing UniFi Apps model:

- trim whitespace;
- accept an optional `SHA256 Fingerprint=` prefix case-insensitively;
- accept colon-separated, space-separated, or contiguous hexadecimal;
- normalize to lowercase contiguous hexadecimal internally;
- reject every non-empty value that is not exactly 64 hexadecimal characters;
- compare expected and actual values using `hmac.compare_digest` or an
  equivalent constant-time comparison.

Pinned verification hashes the exact DER certificate received from the
established TLS socket. It intentionally replaces conventional CA, hostname,
and date validation for that outbound connection. Trust rests on the
administrator independently obtaining and verifying the fingerprint.

No design is acceptable if it sends the authenticated HTTP/MCP request first
and checks the peer certificate afterward. The transport implementation must
establish TLS, inspect and compare the peer certificate, and only then permit
the application protocol request containing credentials or payloads. This
property requires integration tests against the actual MCP HTTP client stack,
not only a fingerprint helper unit test.

## 8. Outbound destinations

Outbound transport is independent of the App's inbound public transport.
Every applicable stored or per-execution destination follows this contract:

| Destination | Behavior |
| --- | --- |
| `http://...` | Allowed; application traffic is unencrypted and must be reported as such |
| `https://...` with no fingerprint | Strict system CA, validity, and hostname/IP validation |
| `https://...` with a fingerprint | Exact certificate fingerprint verification before application data is sent |

This applies to:

- AEP to its configured ACP MCP Worker Endpoint;
- ACP to Bridge or any other administrator-configured MCP connector;
- standalone AEP executions to their source-supplied MCP endpoint.

External MCP servers that do not implement TLS, including existing HA-MCP
deployments, remain supported over HTTP.

The AEP standalone execution contract gains an optional MCP certificate SHA-256
fingerprint. This is consistent with its existing trust boundary: the
authenticated standalone caller already supplies the MCP URL, Bearer, and exact
tool envelope.

Redirect following remains disabled for discovery, initialization, calls,
events, job lifecycle operations, and standalone execution operations.

## 9. Administration UI requirements

All transport and certificate administration is available only through the
existing mandatory HAOS Ingress UI. The UI is bilingual French/English.

Each App displays, per public surface:

- exact functional role;
- internal container port;
- configured HTTP or HTTPS transport;
- a prominent `Non chiffré` / `Unencrypted` badge for HTTP;
- HTTPS certificate source and status;
- certificate fingerprint and validity metadata;
- affected routes or endpoint path;
- corrective action when the surface is unavailable.

ACP specifically displays two clearly differentiated endpoints:

- `Event Intake API` / `API de réception des événements`, path
  `/api/v1/events`, internal port `8098`;
- `MCP Worker Endpoint` / `Endpoint MCP des workers`, path `/mcp`, internal port
  `8100`.

The App cannot safely infer an exact HAOS host-side mapped port in every
deployment. It must not present a guessed URL as authoritative. It may show URL
templates using `<HOME_ASSISTANT_HOST>` and `<HOST_PORT>` and direct the
administrator to the App Network settings for the actual host mapping.

Outbound partner UI rows display one of:

- HTTP — unencrypted;
- HTTPS — system certificate validation;
- HTTPS — pinned SHA-256 certificate.

Regenerating an application certificate requires explicit confirmation and
shows the new fingerprint immediately. A restart applies the new listener
identity.

## 10. English-only operational logging

Runtime logs remain English-only. Logs must not contain Bearers, URL userinfo,
query strings, fragments, event bodies, job inputs, reports, tool arguments, or
tool results.

Every public listener logs its role, transport, bind port, and path at startup.
An HTTP listener additionally emits a warning that names the categories of data
left unencrypted. Examples:

```text
INFO: Event Intake API listening on HTTP port 8098, path /api/v1/events
WARNING: Event Intake API uses unencrypted HTTP; credentials and event payloads are not encrypted by this application

INFO: MCP Worker Endpoint listening on HTTPS port 8100, path /mcp
INFO: Public TLS certificate source: self-generated
INFO: Public TLS certificate SHA-256: AA:BB:CC:DD:...
INFO: Public TLS certificate expires at: 2031-08-23T12:00:00Z
```

Equivalent warnings identify AEP credentials/job inputs/reports and Bridge
namespace credentials/tool arguments/tool results.

Outbound HTTP warnings are emitted when such a destination is configured or
validated and summarized at startup for active stored destinations. AEP emits a
bounded warning when accepting a standalone execution using an HTTP MCP
destination. Warnings must not be repeated for every poll or tool call.

Certificate failures use actionable English messages, for example:

```text
ERROR: Public TLS certificate has expired; renew or regenerate it from the administration interface
ERROR: MCP HTTPS listener was not started because the public TLS certificate is invalid
INFO: Ingress administration remains available for certificate maintenance
```

## 11. Health and watchdog behavior

The existing static HAOS watchdog must not depend on a configurable public
HTTP/HTTPS listener or on trusting an application-generated certificate. A
certificate problem must not create a restart loop that makes Ingress
administration unavailable.

Implementation must provide a transport-independent internal liveness/readiness
strategy suitable for the Supervisor. Its route must not accidentally expose
Ingress administration publicly or merge the ACP Event and MCP route sets.

Readiness distinguishes the application/admin runtime from each public surface.
A public HTTPS certificate failure is reported as a degraded/unavailable public
surface while the administration runtime remains operational.

## 12. Testing requirements

Tests should be automated to the maximum practical extent and cover real socket
behavior, not only configuration parsing.

### Common server tests

- HTTP listener starts and emits the correct English warning;
- HTTPS listener starts with a persistent generated certificate;
- restart retains the same generated certificate and fingerprint;
- explicit regeneration changes the key and fingerprint;
- external certificate and matching key start successfully;
- missing, malformed, mismatched, not-yet-valid, expired, or CA certificates
  prevent only affected HTTPS surfaces from starting;
- Ingress administration remains available after every public TLS failure;
- certificate/private-key permissions and path confinement are enforced;
- TLS version/cipher defaults meet the selected compatibility baseline;
- plaintext HTTP sent to an HTTPS port is rejected.

### Common client tests

- HTTP destination remains functional and produces the expected warning;
- system-trusted HTTPS succeeds;
- untrusted HTTPS without a fingerprint fails;
- correct pinned SHA-256 certificate succeeds;
- absent or malformed fingerprint fails where pinning is selected;
- wrong fingerprint fails before the server receives Authorization or an
  application payload;
- changed certificate fails until the configured fingerprint is replaced;
- expired system-validated certificate fails;
- redirects are not followed;
- credentials and sensitive payloads never appear in logs or reflected errors.

### ACP isolation tests

- Event Intake routes work only on `8098`;
- MCP routes work only on `8100`;
- admin routes work only through the Ingress application on `8099`;
- Event and MCP transports can be selected independently;
- both HTTPS ACP surfaces present the same certificate and fingerprint;
- failure of the shared certificate affects each configured HTTPS surface but
  not an HTTP surface or Ingress administration;
- both ports are independently publishable in the App manifest.

### End-to-end flows

At minimum, exercise:

1. event producer to ACP Event Intake, including an authenticated Home Assistant
   shaped request;
2. AEP to ACP MCP lifecycle: claim, heartbeat, completion/failure, and report;
3. ACP or standalone AEP to Bridge: discovery, exact schemas, tool call, bounded
   result/error, and report delivery where applicable.

Each relevant flow is exercised over HTTP, system-trusted HTTPS, pinned HTTPS,
and mismatch/failure cases. Tests prove that a TLS or fingerprint failure occurs
before secret or payload delivery.

## 13. Implementation sequencing

No public migration or compatibility phase is required before changing the
current repository because the present deployment owner accepts temporary
interruption. This does not narrow the product design: HTTP remains a supported
choice for public installations and external systems.

A safe implementation sequence is:

1. common certificate generation, inspection, fingerprint, path, and outbound
   peer-verification primitives with tests;
2. ACP route/listener split and HAOS port publication;
3. ACP server transport and connector/worker client TLS support;
4. AEP public transport, ACP-boundary pinning, and standalone MCP pinning;
5. Bridge public transport with failure containment inside its shared runtime;
6. bilingual UI, English logs, documentation, threat models, and complete
   cross-App tests;
7. real HAOS validation of ports, watchdog behavior, restart, backup/restore,
   generated certificate persistence, and all three flows.

Implementation details may refine names and internal factoring, but they must
not weaken the decisions or security invariants in this document without an
explicit design revision.
