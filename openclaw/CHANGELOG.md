# Changelog

## 2026.7.1-3 - 2026-08-11

- Allow the privileged startup wrapper to initialize OpenClaw's private `/config`
  directories when the Home Assistant AppArmor profile is active.
- OpenClaw itself still drops permanently to the unprivileged `node` user.

## 2026.7.1-2 - 2026-08-11

- Fix the Docker smoke test to inspect protected persistent state from inside the container.
- Verify and report the subscription-only environment before dropping privileges.

## 2026.7.1-1 - 2026-08-11

- Package the official OpenClaw 2026.7.1 container image for Home Assistant.
- Keep state, OAuth profiles and the agent workspace in private app storage.
- Enforce ChatGPT/Codex OAuth-only operation by removing OpenAI Platform API key variables.
- Add optional direct Streamable HTTP connection to an existing HA-MCP app.
- Restrict the Gateway to its authenticated LAN/VPN port with device authentication enabled.
- Add automated stable-release updates, validation and startup smoke tests.
