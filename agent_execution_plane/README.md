# Agent Execution Plane

Agent Execution Plane is the model reasoning and execution component of the suite. Version `0.3.1` completes Lot 1 with official OpenAI ChatGPT OAuth and polished bilingual model administration while retaining the accepted Lot 0 HAOS shell.

## Responsibility boundary

Agent Execution Plane is an **execution plane only**. It does not own task policy, MCP connector configuration, capability selection or operational authorization.

When Agent Control Plane is used, ACP remains the sole authority for work and capability governance. ACP owns upstream MCP connectors, administrator task/tool selection, virtual capability construction, effective schemas/restrictions such as `fixed_arguments_v1`, authorization and fail-closed upstream invocation.

A claimed ACP job supplies an authoritative `allowed_capabilities` envelope. AEP may verify that those capabilities are still technically present with the expected effective schemas, but it must not derive a different capability set from ACP's complete MCP `tools/list` inventory.

The ACP MCP surface also contains lifecycle operations used by the AEP boundary itself, such as claim, heartbeat, complete and fail. Those lifecycle tools are **not reasoning-model tools** merely because they are callable by the worker identity.

Conceptually:

`ACP/source governance -> exact model capability envelope -> AEP reasoning/execution -> result -> source`

For standalone execution, the caller is the source authority and must supply the exact model-invocable MCP capability envelope for that execution. AEP still does not invent an authorization policy from MCP discovery.

## Install and operate

Add this repository to the Home Assistant App store, install **Agent Execution Plane**, then start it and open its Ingress panel. The administration listener is available only through Ingress on container port `8099`. Container port `8098` is the future standalone API surface; currently it exposes only `/health/live` and `/health/ready`. Its host port can be selected in the App Network settings or left disabled.

The Ingress header offers visible FR/EN and light/dark controls. On first use, language follows a supported browser preference and otherwise falls back to French; theme follows the browser preference. Manual choices are stored only in browser local storage.

The Activity view retains safe operational metadata for 30 days or 10,000 entries, whichever limit is reached first. It never stores prompts, results, credentials, request bodies, reasoning, or tool payloads.

The Models view supports Ollama-compatible and OpenAI-compatible endpoints, deterministic priority, enable/disable, positive per-model timeouts, and encrypted optional provider credentials. OpenAI-compatible explicit validation performs a small tool-call probe that may consume provider usage. Automatic startup health never performs inference.

OpenAI ChatGPT OAuth uses the exactly pinned official Codex `0.144.4` app-server and a shared device-code ChatGPT login. This family accepts no base URL or API key; Codex alone owns OAuth token persistence and refresh under `/data/private/codex-home`.

Lot 1 deliberately provides no execution submission, ACP polling, execution engine, or MCP loop. Lot 2 adds only the source-neutral execution engine; ACP integration itself remains a later boundary lot. See [README.fr.md](README.fr.md) for French documentation.