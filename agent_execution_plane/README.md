# Agent Execution Plane

Agent Execution Plane `0.6.2` is a standalone-capable model reasoning and execution engine. It applies administrator model priority and the common fallback/no-replay rules to exactly the MCP operational capability envelope supplied by the current source.

## Responsibility boundary

AEP does not own tasks, connector configuration, capability selection, authorization, scheduling, or execution history. The standalone caller supplies the objective, JSON input, one execution-scoped MCP endpoint and optional Bearer, the exact MCP tool descriptors, and an optional result schema. The caller cannot select a model. MCP `tools/list` is used only to verify the supplied descriptors and never broadens them.

Provider-native planning/public-information helpers remain separate from MCP operational tools and may not access user infrastructure or AEP private state.

## Agent Control Plane boundary

The optional **Control Plane** view accepts one MCP Streamable HTTP URL and a protected worker Bearer credential. AEP validates the existing ACP lifecycle tools before saving, then polls `jobs_claim_v1` once per second only while a compatible model and the shared execution slot are available. ACP remains the authority for jobs, leases, connector resolution, fixed arguments, capability authorization, retries, and report policy.

For each claim, AEP maps `objective`, `input`, `required_report_schema`, and exactly `allowed_capabilities` into the same execution engine used by standalone requests. ACP lifecycle tools and unrelated tools from `tools/list` never enter the model envelope. AEP heartbeats the lease, prevents new MCP dispatch after lease loss, persists the outcome before `jobs_complete_v1`/`jobs_fail_v1`, retries delivery without rerunning the model, and reconciles interrupted work after restart. ACP availability never affects `/health/ready`, and leaving Control Plane unconfigured preserves full standalone operation.

Connection validation checks the lifecycle tools' input signatures, not only their names. Failure delivery carries the same durable completion key on every retry; one consecutive transient heartbeat error is tolerated, while a second stops execution. An already-expired persisted lease is released locally during restart reconciliation so it cannot retain AEP's shared slot.

## Install and configure

Install the App, configure one or more models in Ingress, and map internal port `8098/tcp` to the desired host port in Home Assistant’s App **Network** section. Administration remains Ingress-only on internal port `8099`.

Open the **API** view and select **Create credential**. Copy the opaque token immediately: only a one-way verifier is stored and the clear token cannot be retrieved later. **Rotate** invalidates the previous token immediately; **Revoke** disables authenticated standalone calls. The Activity journal never records either token.

## Standalone API

All execution routes require `Authorization: Bearer <AEP_STANDALONE_TOKEN>`. Health routes remain public and non-sensitive.

```bash
curl -X POST 'http://HOME_ASSISTANT_HOST:AEP_PORT/api/v1/execute' \
  -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' \
  -H 'Content-Type: application/json' \
  --data '{
    "objective":"Read the requested metric and return a JSON report.",
    "input":{"site":"example"},
    "mcp":{
      "url":"http://MCP_HOST:8000/mcp",
      "bearer_token":"<MCP_BEARER_TOKEN>",
      "tools":[{"name":"read_metric","description":"Read one metric","input_schema":{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}}]
    },
    "result_schema":{"type":"object","properties":{"value":{}},"required":["value"]}
  }'
```

A valid submission returns HTTP `202` with an opaque `execution_id`. Poll without releasing the slot:

```bash
curl -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' \
  'http://HOME_ASSISTANT_HOST:AEP_PORT/api/v1/executions/<EXECUTION_ID>'
```

After durably receiving the result, acknowledge it:

```bash
curl -X POST -H 'Authorization: Bearer <AEP_STANDALONE_TOKEN>' \
  'http://HOME_ASSISTANT_HOST:AEP_PORT/api/v1/executions/<EXECUTION_ID>/ack'
```

GET is repeatable and never frees the slot. Until ACK, another submission returns `busy_pending_result`. Active work returns `busy_active`. If delivery is deliberately abandoned, the Ingress Overview offers a confirmed, execution-ID-bound **Abandon pending result** action.

## Durability and security

The database stores only a minimal active reference or one pending outcome. Objective, input, MCP URL/Bearer, tool descriptors, arguments/results, prompts, conversation, and reasoning remain execution-scoped memory only. The final result exists only in `pending_result` until ACK/abandonment; no completed history is retained.

After restart, an existing pending result is returned unchanged. A standalone execution that was active becomes `execution_interrupted` for the same ID and is never replayed. Request and final API documents are limited to 4 MiB; the Lot 2 limits of 128 capabilities/dispatches, 512 KiB arguments, and 2 MiB tool results remain in force without truncation.

The UI is bilingual FR/EN, supports light/dark mode, and keeps the stable global scrollbar gutter. See [README.fr.md](README.fr.md) for French documentation and [DOCS.md](DOCS.md) for the complete API status table.
