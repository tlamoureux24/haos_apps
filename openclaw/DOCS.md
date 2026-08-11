# OpenClaw Home Assistant App

## Scope

This wrapper uses the official OpenClaw image and adds native Gateway TLS plus
an unprivileged administrative CLI protected by Home Assistant Ingress. It does
not include Homebrew, a browser image, router SSH options or automatic Home
Assistant long-lived token handling.

OpenClaw is reachable only through the published Home Assistant host port. Keep
that port on the trusted LAN or VPN. Do not forward it directly from the public
Internet.

## Configuration

| Option | Default | Purpose |
|---|---|---|
| `timezone` | `Europe/Paris` | IANA timezone used by the Gateway. |
| `gateway_token` | empty | Gateway secret, minimum 24 characters. Set this before first start. |
| `allowed_origins` | `https://homeassistant.local:18789` | Comma-separated exact HTTPS browser origins accepted by Control UI. |
| `mobile_pairing_url` | empty | WebSocket URL reachable from the phone and encoded in mobile pairing QR codes. |
| `openai_oauth_device_login` | `false` | Temporarily start the headless ChatGPT/Codex OAuth device-code flow. |
| `ha_mcp_url` | empty | Existing HA-MCP private Streamable HTTP URL. |

If `gateway_token` is empty, the App generates one at
`/addon_configs/<repository>_openclaw/gateway_token`. Setting the option
explicitly is easier and avoids needing filesystem access to retrieve it.

For access by IP, `allowed_origins` must include the exact URL used by the
browser, for example:

    https://192.168.1.10:18789

Multiple origins are separated by commas. HTTPS through an internal reverse
proxy is also supported:

    https://openclaw.example.lan

OpenClaw terminates HTTPS/WSS itself and generates a persistent self-signed
certificate on first start. Android pins its fingerprint during pairing. A
browser may show a certificate warning until the local certificate is trusted;
this does not require disabling OpenClaw device identity.

The Android app can pair to the Gateway over the LAN or VPN. Current mobile
clients may require HTTPS for non-loopback addresses unless their trusted
private-network cleartext option is explicitly enabled. Prefer an internal TLS
reverse proxy for routine mobile use.

For Docker/HAOS installations, set `mobile_pairing_url` explicitly so QR codes
do not contain the container address. For example:

    wss://192.168.1.15:18789

Use the same private address through a routed VPN, or a `wss://` URL when an
internal TLS reverse proxy is available. The QR carries the temporary bootstrap
credential automatically; the long Gateway token does not need to be typed.

## First start and OpenAI OAuth

1. Set a strong `gateway_token` and the exact `allowed_origins`.
2. Enable `openai_oauth_device_login`, save and restart the App.
3. Open the App log. Follow the printed OpenAI URL and enter the short-lived
   device code with the ChatGPT account that owns the Plus subscription.
4. Wait for `ChatGPT/Codex OAuth login succeeded` in the log.
5. Disable `openai_oauth_device_login`, save and restart the App once so the
   Gateway loads the completed OAuth profile cleanly.
6. Open `https://HOME_ASSISTANT_IP:18789` and enter the Gateway token.
7. Confirm in OpenClaw that the active OpenAI profile is OAuth/subscription
   based before running agent work.

The temporary OAuth helper runs in a private pseudo-terminal because upstream
OpenClaw refuses provider login without an interactive TTY. It runs as the
unprivileged `node` user alongside the Gateway; no shell or terminal is exposed
over the network. The verification code is a short-lived credential, so do not
publish or share the App log while login is active. If the code expires, restart
the App with the option still enabled to request a fresh one.

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

## Administrative CLI

Open the App from the Home Assistant sidebar or press **Open Web UI** on its
Info page. Home Assistant opens an admin-only Ingress terminal running as the
unprivileged `node` user. Run the official commands printed by Android there:

    openclaw devices list
    openclaw devices approve <requestId>

The terminal has no published LAN port and has no root or Docker access.

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

- Port 18789 is the only published LAN port; terminal port 7681 is Ingress-only.
- Internet egress is required for OpenAI OAuth and model requests.
- HA-MCP is reached over its existing local port.
- The container does not use `host_network`, Supervisor APIs, Home Assistant
  APIs, Docker APIs, privileged mode or extra data mounts.
- Device authentication stays enabled over native HTTPS/WSS.
- OpenClaw runs as UID/GID 1000 after a short root-owned mount preparation.

## Updates

A daily workflow reads the latest stable OpenClaw GitHub release, rejects
drafts, prereleases and downgrades, checks the official GHCR manifest for amd64
and arm64, updates the pinned image and App metadata, validates the package,
builds it and probes `/healthz` plus `/readyz`.

The App version follows `OPENCLAW_VERSION-APP_REVISION`. Wrapper-only changes
increment the final revision. A new upstream release resets it to `1`.
