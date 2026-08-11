# OpenClaw for Home Assistant

[Documentation française](README.fr.md)

This Home Assistant App runs the official OpenClaw container image on Home
Assistant OS or a supervised installation. It adds only the Supervisor-facing
packaging and persistent-path preparation required by HAOS.

## Principles

- official version-pinned `ghcr.io/openclaw/openclaw` image;
- upstream non-root `node` runtime;
- no browser, web terminal, Homebrew, Docker socket or host network;
- no OpenAI Platform API key and no metered API fallback;
- ChatGPT/Codex subscription authentication through OpenAI OAuth;
- local/VPN Gateway access on port 18789 with token and device authentication;
- optional direct connection to an existing HA-MCP Streamable HTTP endpoint;
- cold Home Assistant backups and a custom AppArmor profile;
- automated stable upstream updates with validation and smoke tests.

Read [DOCS.md](DOCS.md) before first start, especially the required browser
origin and OAuth setup.

## Upstream

- OpenClaw: https://github.com/openclaw/openclaw
- Docker documentation: https://docs.openclaw.ai/install/docker
- License: MIT
