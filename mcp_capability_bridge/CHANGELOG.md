# Changelog

All notable changes to MCP Capability Bridge will be documented in this file.

## Unreleased

### Design

- Reframed the Bridge as an independent, adapter-oriented MCP server that also integrates with ACP/AEP through their existing generic MCP boundary.
- Made isolated multi-client MCP namespaces, one-time credentials, publication boundaries and per-namespace Web sessions foundational requirements.
- Defined the initial statically packaged SSH and Web interactive adapters without enabling arbitrary runtime plugins.
- Clarified that Web authority is exactly the authority of the configured target account and must be presented as such to administrators.
- Added explicit SSH host-key enrollment, Web origin/network confinement, stale-reference protection, ambiguous-effect handling and secret/result sensitivity rules.
- Aligned the future HAOS Ingress administration UI with ACP/AEP conventions, including FR/EN, light/dark themes, right drawers, top-right actions and stable scrollbar behavior.
- Split browser delivery into packaging/confinement, read-only sessions and interactive-action lots, with real generic-client and ACP/AEP interoperability gates throughout.
- Added a dedicated threat model and replaced the previous implementation sequence with bounded acceptance-driven lots.
