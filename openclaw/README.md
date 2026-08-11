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
- headless OAuth device-code setup from the private Home Assistant App log;
- local/VPN Gateway access on port 18789 with token and device authentication
  by default, plus an explicit temporary HTTP test mode;
- optional direct connection to an existing HA-MCP Streamable HTTP endpoint;
- explicit mobile pairing URL so QR codes advertise the reachable host instead of Docker networking;
- cold Home Assistant backups and a custom AppArmor profile;
- automated stable upstream updates with validation and smoke tests.

Read [DOCS.md](DOCS.md) before first start, especially the required browser
origin and OAuth setup.

## Upstream

- OpenClaw: https://github.com/openclaw/openclaw
- Docker documentation: https://docs.openclaw.ai/install/docker
- License: MIT
