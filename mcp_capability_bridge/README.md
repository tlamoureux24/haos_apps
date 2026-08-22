# MCP Capability Bridge

[Français](README.fr.md) | English

Current release: **1.0.0 stable — Lots 0 through 4 accepted on real HAOS**.

MCP Capability Bridge is an independent Home Assistant OS App that exposes deliberately bounded access to non-MCP technical systems through standard MCP Streamable HTTP tools.

The built-in adapters are:

- bounded administrator-defined SSH capabilities, with a fresh verified connection for every call;
- short-lived interactive Web sessions whose real authority is exactly the authority of the configured target account.

Multiple MCP clients are supported through isolated namespaces. Each namespace has its own one-time Bearer credential, published tool inventory, quotas and Web sessions. Agent Control Plane may connect as an ordinary namespace client and further restrict those tools per task; Agent Execution Plane receives them through ACP's existing generic MCP boundary. Neither component is required for standalone use.

The administration surface is Home Assistant Ingress-only and reuses the established ACP/AEP visual and interaction conventions, including bilingual FR/EN content, light/dark mode, top-right page actions, accessible right drawers, stable scrollbar geometry and responsive layouts.

Authoritative design documents:

- [Project brief](PROJECT_BRIEF.md)
- [Technical design](TECHNICAL_DESIGN.md)
- [Threat model](THREAT_MODEL.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)

Version 1.0.0 is the stable Lot 4 release after successful HAOS installation, persistence, backup/restore, endurance and AppArmor acceptance. SQLite generation 1 is now the production-data compatibility cutoff. See [installation and integration notes](DOCS.md).
