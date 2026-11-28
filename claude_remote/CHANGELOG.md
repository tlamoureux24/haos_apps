# Changelog

## 0.1.17

- Rebuild on the current Home Assistant base image to pick up Alpine
  package updates. The App code is unchanged.
  - `libffi` `3.8.1-r0` → `3.8.2-r0`

## 0.1.16

- Update Claude Code to 2.1.332.

## 0.1.15

- Rebuild on the current Home Assistant base image to pick up Alpine
  package updates. The App code is unchanged.
  - `krb5-libs` `1.22.2-r1` → `1.22.3-r0`
  - `libcrypto3` `3.5.9-r0` → `3.5.9-r1`
  - `libexpat` `2.10.0-r0` → `2.11.0-r0`
  - `libssl3` `3.5.9-r0` → `3.5.9-r1`
  - `libxml2` `2.13.9-r2` → `2.13.9-r3`
  - `zlib` `1.3.2-r1` → `1.4-r0`
  - `zstd-libs` `1.5.7-r2` → `1.6.0-r1`

## 0.1.14

- Update Claude Code to 2.1.331.

## 0.1.13

- Rebuild on the current Home Assistant base image to pick up Alpine
  package updates. The App code is unchanged.
  - `libffi` `3.5.2-r1` → `3.8.1-r0`
  - `pyc` `3.14.10-r1` → `3.14.10-r2`
  - `python3` `3.14.10-r1` → `3.14.10-r2`
  - `python3-ndbm` added (`3.14.10-r3`)
  - `python3-pyc` `3.14.10-r1` → `3.14.10-r2`
  - `python3-pycache-pyc0` `3.14.10-r1` → `3.14.10-r2`

## 0.1.12

- Update Claude Code to 2.1.330.

## 0.1.11

- Update Claude Code to 2.1.329.

## 0.1.10

- Update Claude Code to 2.1.328.

## 0.1.9

- Rebuild on the current Home Assistant base image to pick up Alpine
  package updates. The App code is unchanged.
  - `nginx` `1.30.6-r0` → `1.30.7-r0`

## 0.1.8

- Update Claude Code to 2.1.327.

## 0.1.7

- Update Claude Code to 2.1.326.

## 0.1.6

- Update Claude Code to 2.1.325.

## 0.1.5

- Update Claude Code to 2.1.323.

## 0.1.4

- Update Claude Code to 2.1.322.

## 0.1.3

- Quieter App log: Remote Control redraws its status screen every second,
  which wrote about six lines per second. Only lines that changed since the
  previous screen are logged now, so an idle connection logs nothing and each
  change (reconnecting, connected again, new session) is logged once.

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
