# Changelog

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
