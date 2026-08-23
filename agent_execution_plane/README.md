# Agent Execution Plane

Agent Execution Plane `1.0.1` is a standalone-capable model reasoning and execution engine. It applies administrator model priority and the common fallback/no-replay rules to exactly the MCP operational capability envelope supplied by the current source.

## Responsibility boundary

AEP does not own tasks, connector configuration, capability selection, authorization, scheduling, or execution history. The standalone caller supplies the objective, JSON input, one execution-scoped MCP endpoint and optional Bearer, the exact MCP tool descriptors, and an optional result schema. The caller cannot select a model. MCP `tools/list` is used only to verify the supplied descriptors and never broadens them.

Provider-native planning/public-information helpers remain separate from MCP operational tools and may not access user infrastructure or AEP private state.

## Agent Control Plane boundary

The optional **Control Plane** view accepts one MCP Streamable HTTP URL and a protected worker Bearer credential. AEP validates the existing ACP lifecycle tools before saving, then polls `jobs_claim_v1` once per second only while a compatible model and the shared execution slot are available. ACP remains the authority for jobs, leases, connector resolution, fixed arguments, capability authorization, retries, and report policy.

For each claim, AEP maps `objective`, `input`, `required_report_schema`, and exactly `allowed_capabilities` into the same execution engine used by standalone requests. ACP lifecycle tools and unrelated tools from `tools/list` never enter the model envelope. AEP heartbeats the lease, prevents new MCP dispatch after lease loss, persists the outcome before `jobs_complete_v1`/`jobs_fail_v1`, retries delivery without rerunning the model, and reconciles interrupted work after restart. ACP availability never affects `/health/ready`, and leaving Control Plane unconfigured preserves full standalone operation.

Connection validation checks the lifecycle tools' input signatures, not only their names. Failure delivery carries the same durable completion key on every retry; one consecutive transient heartbeat error is tolerated, while a second stops execution. An already-expired persisted lease is released locally during restart reconciliation so it cannot retain AEP's shared slot.

AEP keeps exactly one optional Control Plane connection. Overview exposes its safe operational state, last successful claim poll, last ACP response, `0`/`1` availability from that claim response, successful poll count, and last bounded error. Editing the connection replaces that singleton after validation; it never creates another ACP source.

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

## Detailed configuration guide

### Network surfaces

| Surface | Internal port | Exposure | Contents |
|---|---:|---|---|
| Administration | `8099` | Ingress only | Overview, Activity, Models, API and Control Plane |
| Standalone | `8098` | Optional host mapping | `/health/live`, `/health/ready`, and `/api/v1/*` |

Map `8098/tcp` only when a standalone caller needs it. Current HTTP examples do not encrypt Bearer headers on the network; keep them on a trusted isolated network or put a trusted TLS reverse proxy in front of AEP.

### Model families

- **Ollama-compatible:** enter the base URL, exact model identifier, positive timeout, and optional credential. Example: `http://192.168.1.20:11434`, `qwen3:14b`.
- **OpenAI-compatible:** enter the compatible API base URL, exact model ID, timeout, and credential. Saving performs an explicit compatibility probe that may consume tokens or credits.
- **ChatGPT OAuth:** start the device login, open the displayed verification URL, enter the one-time code, wait for `connected`, then create a model from the validated catalogue. OAuth material remains in AEP private data.

Priority `1` is tried first. The caller never selects a model. A model in use is locked against editing, disabling, and deletion until execution ends; priority reorder remains safe.

### ACP worker setup

1. Create an ACP identity of type **Worker**.
2. Grant only `jobs.claim`, `jobs.heartbeat`, `jobs.complete`, and `jobs.fail`.
3. Copy its one-time Bearer credential.
4. In AEP **Control Plane**, enter ACP's full endpoint, for example `http://HOME_ASSISTANT_IP:8098/mcp`.
5. Paste the worker credential and save.

AEP validates both names and input schemas of the lifecycle tools. Leaving the credential field empty during a later edit retains the existing encrypted credential. AEP polls only while the shared slot and a compatible model are available. ACP's `allowed_capabilities` is authoritative; lifecycle and unrelated inventory tools never become model-visible.

## Writing the standalone JSON

For readability, save the request in `request.json` instead of writing one long shell line:

```json
{
  "objective": "Read the requested metric and return a JSON report.",
  "input": {
    "site": "main",
    "metric": "temperature"
  },
  "mcp": {
    "url": "http://192.168.1.50:8765/mcp",
    "bearer_token": "REPLACE_WITH_MCP_TOKEN",
    "tools": [
      {
        "name": "read_metric",
        "description": "Read one metric for a site",
        "input_schema": {
          "type": "object",
          "properties": {
            "site": {"type": "string"},
            "name": {"type": "string"}
          },
          "required": ["site", "name"],
          "additionalProperties": false
        }
      }
    ]
  },
  "result_schema": {
    "type": "object",
    "properties": {
      "site": {"type": "string"},
      "metric": {"type": "string"},
      "value": {"type": "number"},
      "unit": {"type": "string"}
    },
    "required": ["site", "metric", "value", "unit"],
    "additionalProperties": false
  }
}
```

Rules that commonly cause `invalid_execution_contract`:

- `objective` must be a non-empty string;
- `input` is mandatory but may be any JSON value, including `null`, an array, or an object;
- `mcp.url` must be HTTP(S) and must not embed username/password;
- `bearer_token` is optional and should be omitted when unused;
- `tools` is mandatory and may be empty; it is the exact authorization envelope;
- each tool contains exactly `name`, `description`, and `input_schema`;
- model/provider/fallback fields and unknown top-level fields are rejected.

The descriptor must match the real MCP `tools/list` entry. Discovery verifies the supplied name and schema but never broadens the tool set.

Validate and submit:

```bash
jq . request.json

curl -X POST 'http://HOME_ASSISTANT_IP:AEP_PORT/api/v1/execute' \
  -H 'Authorization: Bearer REPLACE_WITH_AEP_TOKEN' \
  -H 'Content-Type: application/json' \
  --data-binary @request.json
```

Expected acceptance:

```json
{"execution_id":"019c...","status":"accepted"}
```

Poll until the result is available, process it durably, then ACK it. GET is repeatable; only ACK releases the slot.

## Lifecycle, outcomes, and troubleshooting

```text
idle → active → pending result → ACK → idle
```

There is no hidden queue. Restart keeps a pending outcome unchanged; interrupted standalone work becomes `execution_interrupted` and is not replayed. For ACP work, AEP reconciles the lease and retries delivery with the same completion key without rerunning inference.

When an outcome contains `mcp_effect_possible: true`, the target may have applied the effect even if AEP lost the response. Never implement an automatic retry based only on the failure code.

| Symptom | Check |
|---|---|
| Model unavailable | Provider network, exact model ID, credential, timeout, OAuth account/catalogue |
| ACP connection refused | Full `/mcp` URL, Bearer, four worker permissions, matching lifecycle schemas |
| `invalid_execution_contract` | `jq .`, unknown keys, required tool fields, schema equality with `tools/list` |
| `busy_pending_result` | Poll the displayed ID and ACK after durable consumption |
| Repeated MCP failure | Tool schema, target reachability, Bearer, and `mcp_effect_possible` before retry |

Activity intentionally excludes objectives, inputs, credentials, tool arguments/results, conversations, and reasoning. Model and ACP credentials are encrypted at rest; the standalone token is stored only as a one-way verifier.
