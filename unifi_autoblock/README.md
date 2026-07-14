# UniFi Autoblock

UniFi Autoblock is a Home Assistant app that receives UniFi Alarm Manager webhook events and updates an existing UniFi `IPV4_ADDRESSES` traffic matching list with attacker source IPs.

It is intended for local-only use with UniFi Network API keys.

## How It Works

1. UniFi Alarm Manager sends `Threat Detected and Blocked` events to the app webhook.
2. The app validates the event fields strictly.
3. The app extracts `parameters.src`.
4. Only public global IPv4 source addresses are accepted.
5. The app reads the configured UniFi traffic matching list.
6. The source IP is appended if absent.
7. Entries added by the app expire after the configured TTL.

Existing manual entries are preserved. If an attacker IP is already present in the UniFi list before the app sees it, the app leaves it alone and does not apply TTL cleanup to that entry.

IPv6, private, loopback, link-local, multicast, reserved, and other non-public source addresses are ignored. This prevents internal IDS/IPS alerts from adding local devices to the blocklist.

The app never creates firewall policies. Create a UniFi firewall policy manually that uses your existing traffic matching list as its source.

## Security Defaults

- `dry_run` is enabled by default.
- The UniFi API key is configured as a password option and is never logged.
- No Home Assistant API access is requested.
- No Supervisor API access is requested.
- No host networking is requested.
- No privileged mode is requested.
- Only `/data` is used for app state.

Home Assistant stores app options on the host. Treat Home Assistant backups as sensitive if they include this app's configuration.

## Required UniFi Setup

Create or reuse an IPv4 address traffic matching list in UniFi. Example API response:

```json
{
  "type": "IPV4_ADDRESSES",
  "id": "00000000-0000-0000-0000-000000000000",
  "name": "Auto IDS Blocklist",
  "items": [
    {
      "type": "IP_ADDRESS",
      "value": "203.0.113.10"
    }
  ]
}
```

Then create a firewall rule that blocks traffic from this list toward the protected reverse proxy or exposed service.

If your controller has exactly one site, `unifi_site_id` can be left empty. If exactly one IPv4 address list exists, both `traffic_matching_list_name` and `traffic_matching_list_id` can be left empty. If several sites or several IPv4 lists are found, the app stops and prints the available IDs in the logs.

## UniFi Alarm Manager

Create an alarm with webhook action:

```text
POST http://HOME_ASSISTANT_IP:8080/webhook/TOKEN_PRINTED_IN_THE_APP_LOGS
```

Use the default UniFi webhook content. If `webhook_token` is left empty, the app generates a persistent token on first start and prints the path or full URL in the logs. Set `webhook_base_url` if you want the log to include the complete URL to copy into UniFi Alarm Manager.

## Options

| Option | Description |
| --- | --- |
| `unifi_base_url` | Local UniFi controller URL, for example `https://192.168.1.1`. |
| `unifi_site_id` | Optional UniFi site UUID. Leave empty for auto-detection when the controller has exactly one site. |
| `traffic_matching_list_id` | Optional existing traffic matching list UUID. Leave empty to auto-detect by `traffic_matching_list_name`. |
| `traffic_matching_list_name` | Optional existing traffic matching list name. Leave empty to auto-detect when exactly one IPv4 list exists. |
| `unifi_api_key` | Dedicated UniFi API key. |
| `webhook_token` | Optional long random token used in the webhook URL path. Leave empty to auto-generate and persist one. |
| `webhook_base_url` | Optional base URL used only to print a full Alarm Manager webhook URL in logs, for example `http://HOME_ASSISTANT_IP:8080`. |
| `verify_ssl` | Enable TLS certificate verification for the UniFi controller. |
| `dry_run` | Log what would happen without writing to UniFi. |
| `allowed_destinations` | Optional list of destination IPs to accept. Empty means any destination. |
| `allowed_destination_ports` | UniFi event destination ports to accept, default `443`. This is the attacked service port from `parameters.dpt`, not the app webhook port. |
| `min_severity` | Minimum UniFi event severity. |
| `ban_ttl_days` | TTL for entries managed by this app, default `30`. |
| `max_new_blocks_per_hour` | Rate limit for new blocks. |
| `max_list_size` | Safety limit for the UniFi list. |
| `allowed_webhook_sources` | Optional source CIDRs allowed to call the webhook. |
| `allowlist_cidrs` | Optional CIDRs that must never be blocked. |
| `log_level` | `debug`, `info`, `warning`, or `error`. |

## First Run

Keep `dry_run: true` for the first days. The app will validate events and log the IPs it would add without changing UniFi.

When the logs look correct, set:

```yaml
dry_run: false
```

## Health Check

```text
GET http://HOME_ASSISTANT_IP:8080/health
```
