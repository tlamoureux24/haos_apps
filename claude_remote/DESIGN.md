# Claude Remote App — design

Status: **implemented in 0.1.0** (2026-11-09). User documentation: [README.md](README.md).

## Goal

Use Claude from anywhere (phone, any browser) against the Home Assistant
instance without:

- leaving a laptop switched on at home;
- exposing the HA MCP server (or anything else) to the Internet;
- giving Claude direct access to the Home Assistant configuration, the
  Supervisor or the Core API.

Claude reaches Home Assistant **only through the existing ha-mcp App**
(`homeassistant-ai/ha-mcp`, installed as `81f33d0f_ha_mcp`). Whether Claude can
write is decided in ha-mcp, not in this App.

## Why not reuse a community App

The existing community Apps (Claude Terminal, Claude Terminal Pro,
hass-claude-code, Claude Code UI) are built around direct access: `/config`
mounted read-write, often the `ha` CLI or Supervisor/Core API on top. That is
exactly the access this design removes, so very little of them would survive.
This repository already has the packaging, CI, base-image refresh and
Dependabot plumbing; `studio_code_server` is the closest model (unprivileged
runtime user, Supervisor token stripped, private ha-mcp URL validated).

## Architecture

```
 Phone / browser                       Home Assistant OS host
 ───────────────                       ─────────────────────────────────────────
 Claude app or claude.ai/code          ┌ Claude Remote App (boot: manual) ─────┐
        ▲                              │  claude remote-control  (uid 1000)    │
        │ HTTPS, Anthropic relay       │    └─ MCP client ──────────────┐      │
        └──────────────────────────────┤  outbound 443 only             │      │
                                       │  Ingress: login/status terminal│      │
                                       └────────────────────────────────┼──────┘
                                                                        ▼
                                       ┌ ha-mcp App (81f33d0f_ha_mcp) ─────────┐
                                       │  read_only_mode / disabled_tools      │
                                       │  http://<host>:9583/<secret_path>     │
                                       └───────────────────────────────────────┘
```

- **Remote Control** (`claude remote-control`): the App keeps an outbound
  connection to Anthropic; sessions are driven from the Claude mobile app or
  claude.ai/code. No inbound port, no reverse proxy, no Nabu Casa exposure. The
  user's plan already supports it (used today from the laptop).
- **Ingress** is only for the human admin: first-time `/login`, status, and a
  fallback terminal. HA Ingress already requires an authenticated HA admin.

## Security model

Layers, from strongest to weakest:

1. **ha-mcp server-side policy — the real boundary.** `read_only_mode` (one
   checkbox) or `disabled_tools` for per-tool control. Anything reachable from
   the container with the MCP URL can call every enabled tool, so Claude-side
   rules alone are never sufficient.
2. **No Home Assistant privileges in the App.**
   - no `map` (no `/config`, `/addon_configs`, `/share`, `/addons`);
   - `hassio_api: false`, `homeassistant_api: false`, no `auth_api`;
   - `SUPERVISOR_TOKEN` / `HASS_TOKEN` removed from the Claude process
     environment, as in `studio_code_server`;
   - Claude runs as an unprivileged user (uid 1000) with `HOME=/data/home`.
3. **Claude Code managed policy**, baked into the image under
   `/etc/claude-code/` (not writable by uid 1000, not overridable by user or
   project settings):
   - MCP servers: only `home-assistant`, generated at start from the
     `ha_mcp_url` option (managed MCP configuration);
   - denied tools: `Bash`, `Edit`, `Write`, `NotebookEdit`, `WebFetch`.
     Without a shell, Claude cannot `curl` the MCP URL directly or install
     anything;
   - `bypassPermissions` mode disabled; only managed permission rules apply;
   - `mcp__home-assistant__*` read tools allowed. Write tools stay on **ask**:
     when ha-mcp is switched to read/write, every write still needs an
     approval on the phone (Remote Control relays permission prompts);
   - auto-updater and non-essential telemetry disabled; updates come from the
     pinned image version.
4. **Lifecycle.** `boot: manual`. Start/stop from the HA companion app
   (Settings → Apps, or a dashboard button/script calling
   `hassio.app_start` / `hassio.app_stop`). The same applies to ha-mcp if
   wanted.

What remains reachable: the container has general outbound Internet access
(required for api.anthropic.com; HA Apps cannot restrict egress per
destination). With no shell and no `WebFetch`, Claude has no direct way to
send data elsewhere.

## Configuration options

| Option | Type | Purpose |
| --- | --- | --- |
| `ha_mcp_url` | `password` | Private ha-mcp URL (`http(s)://…/private_<secret>`), validated like `studio_code_server`, never logged |
| `confirm_writes` | `bool` | `true`: ha-mcp read tools allowed, others ask; `false`: every ha-mcp tool allowed |
| `log_level` | list | Usual levels |

Deliberately absent: `packages`, `init_commands`, workspace path, any host
mount. ha-mcp runs with `host_network: true`, so both the LAN URL and the host
gateway form (`http://172.30.32.1:9583/private_<secret>`) reach it.

## Implementation decisions

- **Base image:** Home Assistant base (Alpine), so the daily base refresh
  covers OS packages (`scripts/base_refresh.py`, `app-base-refresh.yml`).
- **Claude Code:** the official musl binary from the npm platform package
  `@anthropic-ai/claude-code-linux-{x64,arm64}-musl`, pinned by version and by
  the SHA-512 of each registry tarball (`sha512sum -c` at build time). No
  Node.js in the image. `claude-remote-update.yml` bumps it daily.
- **Policy:** `/etc/claude-code/managed-settings.json` (static, validated by
  `scripts/validate.py`), `/etc/claude-code/managed-mcp.json` (generated at
  start, `0640 root:claude`, exclusive control over MCP servers) and
  `/etc/claude-code/managed-settings.d/50-ha-mcp.json` (allow rules from
  `confirm_writes`). If the prefix wildcards in the read-tool allow rules do
  not match, those tools simply ask: the failure mode is safe.
- **Remote Control:** `claude remote-control --name "Home Assistant"
  --permission-mode default` in `/data/workspace`, under `script` for a
  pseudo-terminal, restarted with exponential backoff (10 s → 5 min). It only
  starts once `claude auth status` reports a `claude.ai` login and the
  one-time `claude-remote-setup` has been confirmed by a person (trust prompt
  and "Enable Remote Control?" are never auto-answered).
- **Not used:** `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` and
  `DISABLE_GROWTHBOOK` (both disable Remote Control); `claude setup-token`
  (model requests only, cannot run Remote Control).
- **AppArmor:** `apparmor.txt` holds one top-level profile, `claude_remote`
  (s6, nginx, ttyd, the Ingress page and the admin terminal, so it stays
  broad on executables), and two sub-profiles. `claude_remote//claude` is
  entered on every exec of `/usr/local/bin/claude`: network allowed, writes
  limited to `/data/home`, `/data/workspace` and `/tmp`, no capability.
  Anything it executes goes to `claude_remote//claude_shell`: no network, no
  capability, no read of `.credentials.json`, `.claude.json` or
  `managed-mcp.json`, no exec under `/usr/local/bin`. The file declares
  `abi <abi/3.0>`: without it, Ubuntu's parser used a pinned older feature
  set and sub-profiles inherited the parent's network. Without a login,
  Claude Code 2.1.319 executes nothing (checked with strace). The validate
  and update workflows load the profile on the runner kernel and run the
  smoke test under it (`APPARMOR=1`), with a stand-in `claude` that checks
  both sub-profiles.
- **Ingress:** nginx on 8099 (only `172.30.32.2` allowed) in front of the
  status/journal page (Python stdlib, `127.0.0.1:8100`) and ttyd
  (`127.0.0.1:7681`, uid 1000).

## Verified on HAOS only

Container behaviour is covered by `scripts/smoke_test.sh`; these points need
the real device and a signed-in account:

1. `claude remote-control` stays connected unattended under `script`.
2. Permission prompts for HA-MCP tools reach the Claude app.
3. The prefix wildcards in the read-tool allow rules are honoured.
4. `DISABLE_TELEMETRY` does not disable Remote Control (documented as fine
   from Claude Code 2.1.283 on subscription plans).
5. Signed-in Claude Code runs under `claude_remote//claude`: the programs it
   starts once signed in (if any) were not observable in CI.

## Notes on the existing ha-mcp setup

- `read_only_mode` is global to the ha-mcp instance: switching it on also
  restricts the laptop. If both uses need different rights, a second ha-mcp
  instance or `enable_tool_security_policies` would be needed — to be decided
  later.
- ha-mcp uses `host_network: true`, so port 9583 also listens on the LAN;
  the `private_<secret>` path is its only protection there. Independent of
  this App.
