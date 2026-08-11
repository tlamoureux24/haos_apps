# OpenClaw for Home Assistant

[Documentation française](README.fr.md)

This Home Assistant App runs the official OpenClaw container image on Home
Assistant OS or a supervised installation. It adds only the Supervisor-facing
packaging and persistent-path preparation required by HAOS.

## Principles

- official version-pinned `ghcr.io/openclaw/openclaw` image;
- upstream non-root `node` runtime;
- no browser, Homebrew, Docker socket or host network;
- unprivileged OpenClaw CLI through admin-only Home Assistant Ingress;
- no OpenAI Platform API key and no metered API fallback;
- ChatGPT/Codex subscription authentication through OpenAI OAuth;
- OAuth device-code setup through the admin-only Ingress CLI;
- local/VPN HTTPS/WSS Gateway access on port 18789 with token, persistent
  certificate and device authentication;
- optional direct connection to an existing HA-MCP Streamable HTTP endpoint;
- explicit mobile pairing URL so QR codes advertise the reachable host instead of Docker networking;
- cold Home Assistant backups and a custom AppArmor profile;
- automated stable upstream updates with validation and smoke tests.

Read [DOCS.md](DOCS.md) before first start, especially the required browser
origin, mobile pairing URL and CLI-based OAuth setup.

## OAuth setup

Open the admin-only **OpenClaw CLI** through Home Assistant Ingress and run:

```bash
openclaw models auth login --provider openai --device-code
```

Follow the short-lived code flow with the ChatGPT account that owns the
subscription, then restart the App once. Existing OAuth profiles remain in the
private persistent App storage across image updates.

## Upstream

- OpenClaw: https://github.com/openclaw/openclaw
- Docker documentation: https://docs.openclaw.ai/install/docker
- License: MIT
