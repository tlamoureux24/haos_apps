# Agent Gateway

Agent Gateway is an experimental Home Assistant App that mediates work between
authenticated agents and one or more external MCP servers. It exposes only the
virtual tools selected for a task, keeps upstream credentials inside the
gateway, queues executions durably, and stores structured reports and an
append-only audit trail.

French documentation: [README.fr.md](README.fr.md).

## Current capabilities

- generic Streamable HTTP MCP connectors, with optional Bearer authentication;
- independent connector inventories and collision-free virtual tool names;
- tasks composed from selected tools across one or several connectors;
- authenticated MCP clients and authenticated event sources;
- manual, scheduled and event-driven executions;
- cooldown and durable grace incidents for event triggers, with either simple
  mapping-level recovery or bounded aggregation and recovery by stable subject;
- persistent leases, retries, dead letters and human-readable reports;
- reversible task and connector archival without deleting history;
- bounded operational-data retention and verified append-only audit chain;
- French and English Ingress interface with browser detection and a persistent
  manual selector;
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
   connector tools required by that task.
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

## Language

On first use the interface follows a supported browser preference (`fr` or
`en`) and falls back to French. The **FR/EN** header button stores only the
display preference in that browser; it does not change App data. Technical MCP
names, identifiers and upstream data remain unchanged.

## Data, backup, and retention

Configuration, queue state, reports and audit data are stored in the App data
volume and are included in cold Home Assistant backups. The default retention
policy keeps terminal operational data for 90 days. Queued or leased work,
configuration and audit entries are never removed by retention.

During the current single-tester development stage, schema-breaking releases
require removal of App data and a clean reinstall; they do not carry migration
code for disposable data. Unknown schema generations fail closed with a clear
reinstall requirement. A preservation policy will be introduced only when real
non-disposable data exists. No separate configuration export/import is planned
while Home Assistant backups cover coherent recovery.

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
- connector secrets are encrypted at rest and never exposed to agents;
- tool invocation is resolved by task revision, connector, tool and schema
  fingerprint;
- an agent never receives the original connector credential or unrestricted
  connector inventory;
- audit records are hash-chained and can be verified from the interface.

Write-capable or corrective operations remain deferred pending a separate
threat review, explicit approvals, and fail-safe policy design.

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
- there are no write-operation approvals yet;
- multi-instance/high-availability deployment is not supported;
- the App remains experimental and is not intended for internet exposure.
