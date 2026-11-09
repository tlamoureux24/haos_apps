# Changelog

## 0.1.2

- AppArmor profile (`apparmor.txt`). The App profile denies mounts, raw
  sockets and tracing, and limits writes to the App's own data. Claude Code
  runs in its own sub-profile: network for claude.ai and HA-MCP, writes only
  to its home, the workspace and `/tmp`. Every program it starts runs in a
  second sub-profile with no network, no access to the Claude login or the
  HA-MCP URL, and no way to start Claude again.
- CI runs the App under this profile on an AppArmor kernel and checks both
  sub-profiles.

## 0.1.1

- Fix: Remote Control stayed waiting for setup when `claude-remote-setup` was
  closed before its final y/N question. The App now reads the two answers that
  Claude Code itself records (workspace trust, Remote Control enabled), so
  pressing Ctrl-C or closing the terminal is enough.
- The background Remote Control waits while `claude-remote-setup` runs, so two
  "Home Assistant" environments never run at once.

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
