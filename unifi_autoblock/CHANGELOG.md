# Changelog

## 0.4.2

- Fix UniFi API key clearing so the option is kept with an empty value instead of being deleted.

## 0.4.1

- Keep the UniFi API key field visible but empty after local encryption so the key can be re-entered or rotated.
- Make default configuration values blank but valid for Supervisor so resetting to defaults can return the app to a first-setup state.

## 0.4.0

- Encrypt the UniFi API key into local app data and clear it from app configuration after setup.
- Exclude the local UniFi API key decryption key from Home Assistant backups.
- Add Supervisor API access only to clear the stored UniFi API key option after encryption.
- Document that the UniFi API key must be re-entered after restoring without the local decryption key.

## 0.3.19

- Move the webhook port description from static app configuration to translated network strings.

## 0.3.18

- Remove obsolete configuration references from user-facing documentation.

## 0.3.17

- Rewrite README and Home Assistant Documentation tab content to match the current app behavior.
- Document generated webhook secrets, automatic UniFi source filtering, validation rules, and current configuration fields.

## 0.3.16

- Fix the Documentation tab link by using an absolute GitHub README URL.

## 0.3.15

- Switch startup setup logs to English for consistency.
- Move the Home Assistant IP replacement instruction directly below the webhook URL.
- Clarify that `<HOME_ASSISTANT_IP>` must be replaced before using the webhook URL.

## 0.3.14

- Rename destination configuration labels to protected service IPs and ports.
- Remove manual webhook source configuration from the app UI.
- Accept webhook calls only from the UniFi controller host configured in `unifi_base_url`.
- Generate and require a persistent UniFi Alarm Manager Bearer token for webhook calls.

## 0.3.13

- Broaden the AppArmor profile to allow Home Assistant base image startup while keeping AppArmor enabled.

## 0.3.12

- Fix AppArmor profile so the Home Assistant base image S6 init can start.

## 0.3.11

- Use empty strings instead of null defaults for optional auto-detected fields so Supervisor accepts saved configuration.

## 0.3.10

- Improve French configuration translations with accents.
- Clarify that local and non-public IP ranges are ignored automatically without `allowlist_cidrs`.

## 0.3.9

- Fix configuration translation mapping for `verify_ssl` and `allowed_webhook_sources`.
- Clarify `min_severity` and webhook source CIDR descriptions.

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
