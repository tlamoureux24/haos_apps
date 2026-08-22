# MCP Capability Bridge

[Français](README.fr.md) | English

Current release: **0.5.2 — Lot 3B acceptance and operational UI patch**.

MCP Capability Bridge will be an independent Home Assistant OS App that exposes deliberately bounded access to non-MCP technical systems through standard MCP Streamable HTTP tools.

The initial built-in adapters will be:

- bounded administrator-defined SSH capabilities, with a fresh verified connection for every call;
- short-lived interactive Web sessions whose real authority is exactly the authority of the configured target account.

Multiple MCP clients will be supported through isolated namespaces. Each namespace has its own one-time Bearer credential, published tool inventory, quotas and Web sessions. Agent Control Plane may connect as an ordinary namespace client and further restrict those tools per task; Agent Execution Plane receives them through ACP's existing generic MCP boundary. Neither component is required for standalone use.

The administration surface will be Home Assistant Ingress-only and reuse the established ACP/AEP visual and interaction conventions, including bilingual FR/EN content, light/dark mode, top-right page actions, accessible right drawers, stable scrollbar geometry and responsive layouts.

Authoritative design documents:

- [Project brief](PROJECT_BRIEF.md)
- [Technical design](TECHNICAL_DESIGN.md)
- [Threat model](THREAT_MODEL.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)

Version 0.5.0 adds isolated disposable Chromium sessions and target-scoped read-only Web MCP tools. See [installation and acceptance notes](DOCS.md).
