# Agent Gateway

Agent Gateway is a stable Home Assistant App that mediates work between
authenticated agents and one or more external MCP servers. It exposes only the
virtual tools selected for a task, keeps upstream credentials inside the
gateway, queues executions durably, and stores structured reports and an
append-only audit trail.

It acts as a generic application firewall for MCP: deny by default, explicit
administrator configuration is the authorization decision. A discovered tool
that is not selected remains unusable; a tool explicitly selected in a valid
task is authorized only within the exact envelope of that task, revision,
identity, effective schema, and optional argument restrictions. Agent Gateway
does not create a separate authorization class based on whether a tool is
presented as read, write, or administrative.

French documentation: [README.fr.md](README.fr.md).

Public release references: [MCP compatibility](MCP_COMPATIBILITY.md),
[threat model](THREAT_MODEL.md), [implementation plan](IMPLEMENTATION_PLAN.md),
and [changelog](CHANGELOG.md).

## Current capabilities

- generic Streamable HTTP MCP connectors, with optional Bearer authentication;
- independent connector inventories and collision-free virtual tool names;
- tasks composed from selected tools across one or several connectors;
- optional per-tool `fixed_arguments_v1` restrictions that remove selected
  top-level arguments from the agent-visible schema and inject their ordinary
  or protected sensitive values inside the gateway;
- authenticated MCP clients and authenticated event sources;
- manual, scheduled and event-driven executions;
- cooldown and durable grace incidents for event triggers, with either simple
  mapping-level recovery or bounded aggregation and recovery by stable subject;
- persistent leases, retries, dead letters and human-readable reports;
- reversible task and connector archival without deleting history;
- bounded operational-data retention and verified append-only audit chain;
- French and English Ingress interface with an operational cockpit, separated
  configuration drawers, browser detection and a persistent manual selector;
- aggregated operational metrics without secrets or high-cardinality labels.

Agent Gateway does not embed a model and does not run an agent by itself. An
MCP-capable client such as Codex claims queued jobs, invokes the virtual tools
published for the claimed task, and submits the final report.

## Installation

1. Add this repository to the Home Assistant App store.
2. Install **Agent Gateway**.
3. Keep TCP port `8098` unpublished until an MCP client or event source needs
   direct access.
4. Start the App and open its Ingress interface.

The administration listener is available only through authenticated Home
Assistant Ingress. Port `8098` carries the authenticated public MCP and event
API; expose it only on a trusted LAN or VPN.

## First workflow

1. Open **Connectors**, enter a display name and a Streamable HTTP `/mcp` URL,
   then select **Test and add**.
2. Open **Tasks**, write the instructions sent to the agent and select only the
   connector tools required by that task. Leave each tool in **Standard** mode,
   or expand **Restrict this tool** to configure a valid example call and mark
   selected top-level properties as agent-editable, ordinary fixed, or
   sensitive fixed.
3. Open **Identities**, create an MCP client identity with job-processing and
   report permissions, then copy its one-time credential.
4. Configure the MCP client with `http://HOME_ASSISTANT_IP:8098/mcp` and send
   the credential as a Bearer token.
5. Run the task manually, schedule it, or create an authenticated event source
   and trigger.
6. Review **Executions**, **Reports**, and **Audit**.

## Connector and task lifecycle

Disabling is temporary. Archiving removes a resource from normal operational
views while retaining all executions, reports and audit entries. A resource is
restored in a disabled state and must be explicitly reactivated. Agent Gateway
refuses to archive a task or connector while related work is queued or leased.
Archiving a task also pauses its schedules and event triggers.

An active connector can be edited without deleting its tasks. Ordinary editing
can change its display name and optionally replace its endpoint; leaving the new
endpoint empty retains the protected endpoint and Bearer token already stored by
the gateway. The existing endpoint path/query and Bearer token are never
returned to the browser. Use the separate **Rotate secret** action to configure
or replace a Bearer token. A blank rotation is rejected and never clears the
current secret implicitly.

Endpoint replacement and secret rotation always run MCP initialization and tool
discovery again. Network or schema failure retains the last inventory for
inspection but marks the connector unavailable. Dependent tasks fail closed
until the connector is ready and every selected tool still has its recorded
fingerprint. A failed rotation does not replace the stored secret. A successful
rotation replaces the gateway's protected copy; the
old secret is no longer stored or used by Agent Gateway. Revoking that token at
the upstream server remains an upstream administration operation.

## Language

On first use the interface follows a supported browser preference (`fr` or
`en`) and falls back to French. The **FR/EN** header button stores only the
display preference in that browser; it does not change App data. Technical MCP
names, identifiers and upstream data remain unchanged.

## Interface refresh

Each administration view reloads its own data as soon as it is opened, without
requiring a manual browser refresh. The operational **Overview**, **Events**,
**Reports**, and **Audit** views then refresh automatically every 10 seconds,
while **Executions** refreshes every 5 seconds. A bilingual “Updated … ago”
indicator shows the age of the last successful refresh.

Automatic refresh is suspended while the browser tab is hidden, while an
administration drawer is open, or while a detail is expanded in **Events**,
**Reports**, or **Audit**, so reading and editing are not disturbed. Refreshing
resumes automatically afterwards; returning to a previously hidden browser tab
immediately refreshes the active view.

## Data, backup, and retention

Configuration, queue state, reports and audit data are stored in the App data
volume and are included in cold Home Assistant backups. The default retention
policy keeps terminal operational data for 90 days. Queued or leased work,
configuration and audit entries are never removed by retention.

Development is now closed and persisted Agent Gateway data is considered
non-disposable starting with existing 0.46.8 installations. Any future release
that changes the SQLite schema must preserve existing data through an explicit,
tested upgrade path. Routine App-data deletion or a clean reinstall is no longer
an acceptable schema-upgrade strategy. If a database cannot be upgraded safely,
startup must fail closed without partially altering it and the release must
document the required backup/recovery path. No separate configuration
export/import is planned while Home Assistant backups cover coherent recovery.

## Grace incidents and subject correlation

A trigger with a grace period can use **Simple** correlation or **Aggregated by
subject** correlation. Aggregated mode requires every alert and recovery to
carry the same non-empty, stable `subject` object for one resource. Changing
observations belong in `attributes`. The first alert fixes the deadline;
additional subjects do not extend it. Recoveries remove only their matching
subject, and one job is created at expiry for all subjects still active.

Incidents and their subject counts remain visible under **Triggers**. Promotion
is atomic and bounded; an incident that cannot be queued after bounded retries
becomes visibly blocked and can be retried by an administrator. Incoming events
remain individually retained and audited.

## Security boundaries

- the application listeners run as an unprivileged user under AppArmor;
- administration is isolated from the public MCP/event listener;
- discovery of a tool grants no execution right;
- only tools explicitly selected in the valid task revision are exposed and
  invocable by the authorized identity;
- explicit administrator selection of a tool is its authorization, regardless
  of any semantic read, write, or administrative label;
- any tool or argument outside the configured capability envelope is rejected;
- connector secrets are encrypted at rest and never exposed to agents;
- sensitive fixed arguments are encrypted at rest and redacted by key and by
  transient value from every upstream result before it reaches an agent;
- fixed arguments are absent from the virtual schema, cannot be overridden by
  an agent, and are injected only after validation of the reduced call;
- admitted MCP input schemas use JSON Schema Draft 2020-12 and are enforced in
  full before an upstream call; unknown constraints, formats, dialects and
  external references fail closed;
- reachable connectors whose schemas cannot be admitted are marked `invalid`
  with their precise `last_error_code`, while transport failures remain
  `unreachable`;
- tool invocation is resolved by task revision, connector, tool and schema
  fingerprint;
- an agent never receives the original connector credential or unrestricted
  connector inventory;
- audit records are HMAC-chained and can be verified from the interface;
- the cockpit never traverses the chain: it reads bounded state while the
  authenticated anchor is revalidated before each incremental advance;
- a full verification runs at startup, every 24 hours, on request, and
  immediately after any inconsistency without replacing the last valid
  checkpoint when it fails.

The security model does not rely on a second transactional approval step: the
gateway strictly enforces the policy explicitly configured by the administrator
and fails closed whenever it can no longer prove that an invocation remains
inside that envelope.

## Test MCP server

`scripts/fake_mcp_server.py` is a harmless read-only acceptance server. It
publishes a fake `ha_get_addon` tool specifically to prove that two connectors
may expose the same upstream name while Agent Gateway gives the agent two
unique virtual names.

```bash
python3 -m pip install 'mcp==1.28.1'
python3 agent_gateway/scripts/fake_mcp_server.py --host 0.0.0.0 --port 8765
```

Stop the server and remove any temporary firewall rule after the test.

## Known limits

- Streamable HTTP is the only connector transport currently supported;
- no autonomous worker is bundled: an external MCP client must process jobs;
- multi-instance/high-availability deployment is not supported;
- direct internet exposure is not supported; use a trusted LAN or VPN.
