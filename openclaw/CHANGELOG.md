# Changelog

## 2026.7.1-1 - 2026-08-11

- Package the official OpenClaw 2026.7.1 container image for Home Assistant.
- Keep state, OAuth profiles and the agent workspace in private app storage.
- Enforce ChatGPT/Codex OAuth-only operation by removing OpenAI Platform API key variables.
- Add optional direct Streamable HTTP connection to an existing HA-MCP app.
- Restrict the Gateway to its authenticated LAN/VPN port with device authentication enabled.
- Add automated stable-release updates, validation and startup smoke tests.
