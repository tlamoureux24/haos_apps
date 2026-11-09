# Changelog

## 0.1.0

- First release: Claude Code 2.1.319 in Remote Control mode, driven from the
  Claude app or claude.ai/code, with outbound connections only.
- Claude can only use the private HA-MCP server set in `ha_mcp_url`; no other
  MCP server can be added and no Home Assistant API or folder is available.
- Built-in shell, file, web and subagent tools are denied by a managed policy;
  HA-MCP read tools run directly and other tools ask for approval
  (`confirm_writes`).
- Ingress page with status, bilingual activity journal and an admin terminal
  for the one-time `claude-remote-setup`.
