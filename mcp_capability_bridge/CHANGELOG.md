# Changelog

All notable changes to MCP Capability Bridge will be documented in this file.

## 0.1.0 — 2026-08-21

### Added

- Added the installable HAOS App shell with synchronized metadata, authoritative assets and bilingual installation documentation.
- Added one unprivileged Python runtime owning isolated Ingress 8099 and public 8098 ASGI applications.
- Exposed only non-sensitive liveness/readiness routes on the public surface; MCP remains intentionally absent until Lot 1.
- Added generation-one metadata-only SQLite initialization and graceful shared-listener shutdown.
- Added the ACP/AEP visual foundation with FR/EN, light/dark themes, stable scrollbar geometry, responsive navigation, top-right action and accessible right drawer.
- Added a bounded AppArmor profile based on observed ACP/AEP S6 runtime executables and exact Bridge persistence paths.
- Added Lot 0 unit, repository, image, listener-isolation, restart and executable-inventory validation.

### Design

- Reframed the Bridge as an independent, adapter-oriented MCP server that also integrates with ACP/AEP through their existing generic MCP boundary.
- Made isolated multi-client MCP namespaces, one-time credentials, publication boundaries and per-namespace Web sessions foundational requirements.
- Defined the initial statically packaged SSH and Web interactive adapters without enabling arbitrary runtime plugins.
- Clarified that Web authority is exactly the authority of the configured target account and must be presented as such to administrators.
- Added explicit SSH host-key enrollment, Web origin/network confinement, stale-reference protection, ambiguous-effect handling and secret/result sensitivity rules.
- Aligned the future HAOS Ingress administration UI with ACP/AEP conventions, including FR/EN, light/dark themes, right drawers, top-right actions and stable scrollbar behavior.
- Split browser delivery into packaging/confinement, read-only sessions and interactive-action lots, with real generic-client and ACP/AEP interoperability gates throughout.
- Added a dedicated threat model and replaced the previous implementation sequence with bounded acceptance-driven lots.
