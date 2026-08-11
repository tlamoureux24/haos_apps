# Changelog

## 2026.7.1-9 - 2026-08-11

- Replace the temporary cleartext browser mode with OpenClaw's native HTTPS/WSS
  listener and a persistent auto-generated TLS certificate.
- Require secure HTTPS origins and a secure `wss://` mobile pairing URL.
- Add an unprivileged OpenClaw administrative CLI through admin-only Home
  Assistant Ingress; no terminal port is published on the LAN.
- Pin and verify the upstream ttyd binary independently for amd64 and aarch64.

## 2026.7.1-8 - 2026-08-11

- Add an explicit mobile pairing WebSocket URL so QR codes advertise the HAOS
  host or VPN-reachable address instead of the internal Docker address.
- Preserve automatic bootstrap-token transfer: mobile users no longer need to
  type the long Gateway token during QR pairing.

## 2026.7.1-7 - 2026-08-11

- Make the Docker smoke-test log assertion immune to an expected SIGPIPE when
  the searched startup line is followed by additional Gateway output.

## 2026.7.1-6 - 2026-08-11

- Give the internal OAuth pseudo-terminal a fixed 120-column size so the
  device URL and code remain readable in Home Assistant logs.
- Disable unnecessary terminal colors in the headless OAuth helper.

## 2026.7.1-5 - 2026-08-11

- Add an opt-in ChatGPT/Codex OAuth device-code login flow for headless Home
  Assistant installations.
- Keep the Gateway available while the temporary login process prints its URL
  and short-lived code to the private App log.
- Run both OAuth and Gateway processes as the unprivileged upstream `node` user
  and persist the resulting OpenAI auth profile across App updates.

## 2026.7.1-4 - 2026-08-11

- Add an explicit, opt-in LAN/VPN test mode for the Control UI over plain HTTP.
- Keep Gateway token authentication and exact browser-origin checks enabled in
  that mode while disabling only Control UI browser device identity.
- Document the security tradeoff in English and French; secure device identity
  remains the default.

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
