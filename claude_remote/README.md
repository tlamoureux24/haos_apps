# Claude Remote

Documentation: [Français](README.fr.md) | [English](README.md)

Claude Remote runs [Claude Code](https://code.claude.com/docs) in **Remote Control** mode inside Home Assistant. You use it from the Claude mobile app or claude.ai/code, with no computer left on and nothing exposed to the Internet.

Claude has **no direct access** to Home Assistant: it only goes through the MCP server of the [HA-MCP](https://github.com/homeassistant-ai/ha-mcp) App. Read-only or read/write access is set in HA-MCP, not here.

## How it works

```text
Phone / browser ──HTTPS──▶ Anthropic ◀──outbound HTTPS── Claude Remote ──▶ HA-MCP ──▶ Home Assistant
```

- The App only opens an **outbound** connection to Anthropic. No inbound port, no reverse proxy.
- The sidebar page (Ingress) is for setup, status and the activity journal, and is restricted to HA administrators.
- `boot: manual`: the App only runs when you start it.

## Requirements

- A Claude subscription (Pro, Max, Team or Enterprise). Remote Control does not work with an API key.
- The HA-MCP App installed and started.

## Setup

1. Install the App from this repository.
2. In the HA-MCP App, copy the private URL, shaped like `http://192.168.1.15:9583/private_xxxx`.
3. In the Claude Remote configuration, paste it into **Private HA-MCP URL**, then start the App.
4. Open the App, then **Open terminal**, and run:

   ```bash
   claude-remote-setup
   ```

   - Step 1: sign in to your Claude account. Open the link on any device; if a code is shown, paste it into the terminal.
   - Step 2: Remote Control runs once in the foreground. Accept its questions (trust `/data/workspace`, enable Remote Control). When it shows it is ready, press Ctrl-C or close the terminal.
5. Within 20 seconds Remote Control runs in the background. On the phone: Claude app → **Code** → **Home Assistant** environment.

## Options

| Option | Description |
| --- | --- |
| `ha_mcp_url` | Private URL shown by the HA-MCP App, ending in `/private_<secret>`. Empty: Claude has access to nothing. It is never written to the logs or the journal. |
| `confirm_writes` | On by default: HA-MCP read tools (`ha_get_*`, `ha_list_*`, `ha_search*`, `ha_config_get_*`, `ha_config_list_*`, `ha_eval_template`) run directly and every other tool asks for approval in the Claude app. Off: every HA-MCP tool runs without asking. |
| `log_level` | Verbosity of the App log. |

## Security model

From strongest to weakest:

1. **HA-MCP is the real boundary.** Tick `read_only_mode` in the HA-MCP App for strict read-only access, or use `disabled_tools` per tool. This setting applies to every HA-MCP client, including your computer.
2. **No Home Assistant privileges in the App.**
   - No mounted folder (`/config`, `/share`, App configurations…).
   - `hassio_api: false` and `homeassistant_api: false`.
   - No published port; Ingress only accepts the HA proxy.
   - Claude Code and the terminal run as an unprivileged user (uid 1000) with a cleared environment: no Supervisor token.
3. **Claude Code policy baked into the image** (`/etc/claude-code`, not changeable by the user or a project).
   - Only the `home-assistant` MCP server exists. No other server can be added, from the terminal, the phone or claude.ai connectors.
   - Built-in tools are denied: shell (`Bash`), file read and write, `WebFetch`, `WebSearch`, subagents, and so on. Claude can therefore neither call the MCP URL itself nor read the file that holds it.
   - Modes that skip approvals (`bypassPermissions`, `auto`) are disabled, and only the App's hooks and rules apply.
   - Auto-updates, telemetry and error reporting are off. Claude Code is updated through a new App version, pinned by version and SHA-512 digest.
4. **AppArmor profile, enforced by the kernel.** Claude Code runs in its own sub-profile: it can write only to its home, the workspace and `/tmp`, and can start no App script. Any program it starts (shell, ripgrep…) lands in a second sub-profile with no network, no access to the Claude login or the HA-MCP URL, and no way to start Claude again. Even if the policy above were bypassed, a shell started by Claude could not send anything out.
5. **Lifecycle.** Start and stop the App, and the HA-MCP App if you like, when you need them: from the HA companion app, or with a dashboard button calling `hassio.app_start` / `hassio.app_stop`.

What remains possible: the container keeps outbound Internet access, which it needs to reach Anthropic. Without a shell or `WebFetch`, Claude has no direct way to send data elsewhere, and AppArmor keeps any program it starts off the network.

The admin terminal gives a shell as the App's unprivileged user. It is restricted to HA administrators and has no Home Assistant token or configuration access.

## Data and backups

- `/data/home`: Claude account, settings and session history.
- Credentials (`.credentials.json`) and conversation history are **excluded from HA backups**. After a restore, run `claude-remote-setup` again.
- The claude.ai sign-in eventually expires; Claude Code warns 3 days ahead. Remote Control then stops and the App goes back to "waiting for sign-in": run `claude auth login` in the terminal.
- The activity journal (`/data/activity.jsonl`) only holds technical events, kept for 30 days or 10,000 entries at most. It never contains prompts, tool results, URLs or credentials.

## Troubleshooting

| Symptom | Hint |
| --- | --- |
| "waiting for sign-in" | Run `claude-remote-setup` or `claude auth login` in the terminal. |
| "waiting for setup" | Run `claude-remote-setup` again and accept both questions (trust `/data/workspace`, then `y`). |
| HA-MCP unreachable | Check that the HA-MCP App is started and the URL is right. If the HA IP changes, try `http://172.30.32.1:9583/private_xxxx`. |
| Remote Control keeps restarting | Read the App log. |
