# UniFi Autoblock Documentation

UniFi Autoblock receives UniFi Alarm Manager webhook events and adds public IPv4 attacker addresses to an existing UniFi `IPV4_ADDRESSES` traffic matching list.

The app does not create firewall rules. Create a UniFi firewall policy manually that blocks traffic from your traffic matching list toward the protected reverse proxy or exposed service.

## Security

- `dry_run` is enabled by default.
- The UniFi API URL must use HTTPS.
- The UniFi API key is accepted as a password option, encrypted locally, and then the configuration field is cleared.
- The local decryption key is excluded from Home Assistant backups.
- The webhook URL token and Bearer token are generated automatically.
- Webhook calls are accepted only from the UniFi controller host configured in `unifi_base_url`.
- No Home Assistant API, host network, privileged mode, or Docker access is requested.
- Supervisor API access is used only to clear the UniFi API key field after encryption.

After restoring a Home Assistant backup or reinstalling the app without its local decryption key, enter the UniFi API key again in the app configuration.

## UniFi Alarm Manager

Start the app and copy the setup values from the logs:

```text
UniFi Alarm Manager webhook URL: http://<HOME_ASSISTANT_IP>:37989/webhook/...
Replace <HOME_ASSISTANT_IP> with the local Home Assistant IP address
UniFi Alarm Manager authentication: Bearer ...
Automatically accepted webhook source: 192.168.1.1/32
```

In UniFi Alarm Manager, configure:

```text
Delivery method: POST
Delivery URL: http://HOME_ASSISTANT_IP:37989/webhook/TOKEN_FROM_LOGS
Authentication: Bearer
Bearer token: BEARER_TOKEN_FROM_LOGS
Content: Default Content
```

`HOME_ASSISTANT_IP` must be replaced with the local IP address of Home Assistant.

## Main Options

| Option | Description |
| --- | --- |
| `unifi_base_url` | HTTPS URL of the local UniFi controller, for example `https://192.168.1.1`. The host is also used as the only accepted webhook source. |
| `unifi_api_key` | Dedicated UniFi API key. Enter it on first setup or after restoring from backup. The app encrypts it locally and clears this field automatically. |
| `verify_ssl` | Enable UniFi TLS certificate verification. Keep `false` for self-signed UniFi certificates. |
| `dry_run` | Validate events without writing to UniFi. |
| `unifi_site_id` | Optional site UUID. Leave empty for auto-detection when there is exactly one site. |
| `traffic_matching_list_id` | Optional UniFi traffic matching list UUID. Leave empty for auto-detection. |
| `traffic_matching_list_name` | Optional UniFi traffic matching list name. Leave empty when exactly one IPv4 list exists. |
| `allowed_destinations` | Internal IPs of protected services. Empty accepts any destination IP from valid IDS/IPS events. |
| `allowed_destination_ports` | Protected service ports from IDS/IPS events, default `443`. This is not the app webhook port. |
| `min_severity` | Ignore UniFi events below this severity. Keep `0` to accept all severities. |
| `ban_ttl_days` | Days before app-managed entries expire. Manual UniFi list entries are preserved. |
| `allowlist_cidrs` | Optional public CIDRs that must never be blocked. Local and non-public ranges are ignored automatically. |
| `log_level` | `debug`, `info`, `warning`, or `error`. |

## Validation Rules

The app only processes events where:

- `name` is `Threat Detected and Blocked`
- `parameters.act` is `blocked`
- `parameters.UNIFIdirection` is `incoming`
- `parameters.UNIFIpolicyType` is `IDS/IPS`
- the destination IP and port match the configured protected service filters
- the source is a public global IPv4 address

IPv6, private, local, loopback, link-local, multicast, reserved, and allowlisted source addresses are ignored.

## Full README

See the [UniFi Autoblock README on GitHub](https://github.com/tlamoureux24/haos_apps/blob/main/unifi_autoblock/README.md) for the full documentation.
