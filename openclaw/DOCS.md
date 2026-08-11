# OpenClaw Home Assistant App

## Scope

This is a thin wrapper around the official OpenClaw image. It deliberately does
not include the third-party HA add-on's web terminal, Homebrew, browser image,
router SSH options or automatic Home Assistant long-lived token handling.

OpenClaw is reachable only through the published Home Assistant host port. Keep
that port on the trusted LAN or VPN. Do not forward it directly from the public
Internet.

## Configuration

| Option | Default | Purpose |
|---|---|---|
| `timezone` | `Europe/Paris` | IANA timezone used by the Gateway. |
| `gateway_token` | empty | Gateway secret, minimum 24 characters. Set this before first start. |
| `allowed_origins` | `http://homeassistant.local:18789` | Comma-separated exact browser origins accepted by Control UI. |
| `allow_insecure_http` | `false` | Temporarily disable Control UI browser device identity for private LAN/VPN HTTP testing. |
| `ha_mcp_url` | empty | Existing HA-MCP private Streamable HTTP URL. |

If `gateway_token` is empty, the App generates one at
`/addon_configs/<repository>_openclaw/gateway_token`. Setting the option
explicitly is easier and avoids needing filesystem access to retrieve it.

For access by IP, `allowed_origins` must include the exact URL used by the
browser, for example:

    http://192.168.1.10:18789

Multiple origins are separated by commas. HTTPS through an internal reverse
proxy is also supported:

    https://openclaw.example.lan

Browsers cannot create OpenClaw device identity when the Control UI is opened
over plain HTTP on a non-localhost address. For a temporary test restricted to
the trusted LAN/VPN, set `allow_insecure_http: true`. Gateway token auth and
the exact-origin allowlist remain enforced, but browser pairing, per-device
identity and per-device revocation are disabled. HTTP traffic, including the
token and conversations, is not encrypted. Never enable this option on a port
reachable from the public Internet; turn it off again when HTTPS is available.

The Android app can pair to the Gateway over the LAN or VPN. Current mobile
clients may require HTTPS for non-loopback addresses unless their trusted
private-network cleartext option is explicitly enabled. Prefer an internal TLS
reverse proxy for routine mobile use.

## First start and OpenAI OAuth

1. Set a strong `gateway_token` and the exact `allowed_origins`.
2. Start the App and open `http://HOME_ASSISTANT_IP:18789`.
3. Enter the Gateway token. Approve the browser when requested unless
   `allow_insecure_http` is enabled.
4. Complete OpenClaw onboarding and select OpenAI ChatGPT/Codex OAuth.
5. Sign in with the ChatGPT account that owns the Plus subscription.
6. Confirm in OpenClaw that the active OpenAI profile is OAuth/subscription
   based before running agent work.

The launcher always removes `OPENAI_API_KEY`, `CODEX_API_KEY`,
`OPENAI_ADMIN_KEY` and `OPENAI_PROJECT_ID` from the Gateway environment. It
does not offer API-key options. Do not manually add an API-key auth profile in
OpenClaw. Realtime voice features that require the public OpenAI Platform API
will remain unavailable rather than incur metered billing.

## Existing HA-MCP App

Read the HA-MCP App logs and copy its local private URL, for example:

    http://192.168.1.10:9583/private_xxxxxxxxxxxxxxxxx

Paste it into `ha_mcp_url` and restart OpenClaw. The wrapper registers that URL
as the `home-assistant` Streamable HTTP MCP server. It does not start another
HA-MCP instance and it does not need a Home Assistant long-lived token.

Leaving `ha_mcp_url` empty removes only the wrapper-managed `home-assistant`
entry. Other MCP servers configured inside OpenClaw are preserved.

The private URL is a credential. It is stored in private App options and in
OpenClaw's private configuration, both included in Home Assistant backups.

## Persistent data

All mutable data lives below the App's private `addon_config` mount:

| Path | Content |
|---|---|
| `.openclaw/` | Gateway configuration, sessions and OpenClaw state |
| `.config/openclaw/` | OAuth/auth-profile secret material |
| `workspace/` | Agent files and Git working copies |
| `gateway_token` | Generated token when the option is left empty |

Image replacement never overwrites these paths. Home Assistant cold backups
include them while the App is stopped, avoiding partially written session data.

## Git

The official image includes Git. Repositories may be cloned into the persistent
workspace by OpenClaw. Keep credentials outside repositories and start with a
repository-scoped identity. Branch protection and confirmation before changes
to `main`, releases, secrets or workflows remain recommended.

## Network and security

- Port 18789 is the only published port.
- Internet egress is required for OpenAI OAuth and model requests.
- HA-MCP is reached over its existing local port.
- The container does not use `host_network`, Supervisor APIs, Home Assistant
  APIs, Docker APIs, privileged mode or extra data mounts.
- Device authentication stays enabled by default. The explicit
  `allow_insecure_http` test option disables it only for Control UI operator
  sessions; Gateway token authentication and allowed origins remain active.
- OpenClaw runs as UID/GID 1000 after a short root-owned mount preparation.

## Updates

A daily workflow reads the latest stable OpenClaw GitHub release, rejects
drafts, prereleases and downgrades, checks the official GHCR manifest for amd64
and arm64, updates the pinned image and App metadata, validates the package,
builds it and probes `/healthz` plus `/readyz`.

The App version follows `OPENCLAW_VERSION-APP_REVISION`. Wrapper-only changes
increment the final revision. A new upstream release resets it to `1`.
