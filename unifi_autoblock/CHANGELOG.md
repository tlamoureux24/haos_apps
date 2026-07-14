# Changelog

## 0.3.8

- Revert AppArmor configuration to boolean form for Supervisor compatibility.

## 0.3.7

- Reference the custom AppArmor profile by name in app configuration.

## 0.3.6

- Add a dedicated AppArmor profile.
- Add app URL metadata, experimental stage, and Supervisor watchdog health check.

## 0.3.5

- Remove rate limiting and arbitrary list-size limiting.
- Save a single overwritten JSON backup of the UniFi traffic matching list before every PUT.
- Document that already-present IPs are not added again.

## 0.3.4

- Require `unifi_base_url` to use HTTPS to protect the UniFi API key in transit.
- Keep `verify_ssl: false` supported for self-signed UniFi certificates.

## 0.3.3

- Remove `webhook_token` from app configuration.
- Always generate and persist the webhook token internally.
- Print the webhook URL on every start, using the configured host port when available.

## 0.3.2

- Remove `webhook_base_url` to keep setup simpler.
- Print a prominent UniFi Alarm Manager webhook URL with the generated token in the logs.

## 0.3.1

- Change default webhook port from 8080 to high port 37989 to reduce add-on port collisions.
- Document that the host port can be changed in the app network settings.

## 0.3.0

- Auto-detect the IPv4 traffic matching list when exactly one exists and no name or ID is configured.
- Generate and persist a webhook token when `webhook_token` is left empty.
- Add optional `webhook_base_url` to print a full Alarm Manager URL in the logs.

## 0.2.0

- Add automatic UniFi site discovery when `unifi_site_id` is empty.
- Add automatic traffic matching list discovery by `traffic_matching_list_name` when `traffic_matching_list_id` is empty.
- Fail safely with actionable logs when multiple sites or duplicate list names are found.

## 0.1.1

- Rename `allowed_ports` to `allowed_destination_ports` for clearer app configuration.
- Document that only public global IPv4 source addresses are blocked.
- Clarify that IPv6 and internal IDS/IPS alerts are ignored.

## 0.1.0

- Initial release.
- Local UniFi Alarm Manager webhook endpoint.
- Strict IDS/IPS event validation.
- Public IPv4-only blocking.
- Existing UniFi traffic matching list update.
- Configurable TTL, dry-run mode, rate limit, allowlist, and webhook source filter.
