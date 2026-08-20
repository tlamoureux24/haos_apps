# Agent Execution Plane

Agent Execution Plane is the model reasoning and execution component of the suite. Version `0.1.2` implements only the Lot 0 executable Home Assistant OS App shell: secure listeners, Ingress administration, health checks, generation-1 SQLite plumbing, and a safe persistent activity journal.

## Install and operate

Add this repository to the Home Assistant App store, install **Agent Execution Plane**, then start it and open its Ingress panel. The administration listener is available only through Ingress on container port `8099`. Container port `8098` is the future standalone API surface; in Lot 0 it exposes only `/health/live` and `/health/ready`. Its host port can be selected in the App Network settings or left disabled.

The Ingress header offers visible FR/EN and light/dark controls. On first use, language follows a supported browser preference and otherwise falls back to French; theme follows the browser preference. Manual choices are stored only in browser local storage.

The Activity view retains safe operational metadata for 30 days or 10,000 entries, whichever limit is reached first. It never stores prompts, results, credentials, request bodies, reasoning, or tool payloads.

Lot 0 deliberately provides no model provider, execution submission, ACP polling, or MCP loop. See [README.fr.md](README.fr.md) for French documentation.
