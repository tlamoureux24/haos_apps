# UniFi Autoblock

UniFi Autoblock is a Home Assistant app that receives local UniFi Alarm Manager webhook events and updates an existing UniFi `IPV4_ADDRESSES` traffic matching list with attacker source IPs.

The app is designed for local-only deployments with UniFi Network API keys. It does not create firewall rules by itself; it updates the IP list that your existing UniFi firewall policy already uses.

## Current Design

1. UniFi IDS/IPS detects and blocks an incoming threat.
2. UniFi Alarm Manager sends the default webhook payload to UniFi Autoblock.
3. UniFi Autoblock verifies the webhook URL token, Bearer token, and source IP.
4. The app validates the UniFi event fields.
5. The app accepts only public global IPv4 attacker addresses from `parameters.src`.
6. The app reads the configured UniFi traffic matching list.
7. The app backs up the current list JSON to `/data/last_traffic_matching_list_backup.json` before every write.
8. If the attacker IP is not already present, the app appends it to the UniFi list and verifies the update.
9. Entries managed by the app expire after the configured TTL.

Existing manual entries are preserved. TTL cleanup only applies to IPs that UniFi Autoblock added and tracks in `/data/state.json`.

IPv6, private, loopback, link-local, multicast, reserved, and other non-public source addresses are ignored automatically. Internal IDS/IPS alerts should therefore not add local devices to your blocklist.

## Security Model

- `dry_run` is enabled by default.
- `unifi_base_url` must use `https://`; plain HTTP is rejected to protect the UniFi API key in transit.
- `verify_ssl: false` is supported for self-signed UniFi controller certificates, but the connection still uses HTTPS encryption.
- The UniFi API key is configured as a password option and is never logged.
- The webhook URL token is generated automatically and stored in `/data/state.json`.
- The UniFi Alarm Manager Bearer token is generated automatically and stored in `/data/state.json`.
- Webhook calls are accepted only from the host resolved from `unifi_base_url`, for example `https://192.168.1.1` becomes `192.168.1.1/32`.
- No Home Assistant API access is requested.
- No Supervisor API access is requested.
- No host networking is requested.
- No privileged mode is requested.
- Only `/data` is used for app state.

Home Assistant stores app options and backups on the host. Treat Home Assistant backups as sensitive if they include this app's configuration, because they may contain the UniFi API key.

## Required UniFi Setup

Create or reuse an IPv4 address traffic matching list in UniFi. Example API shape:

```json
{
  "type": "IPV4_ADDRESSES",
  "id": "00000000-0000-0000-0000-000000000000",
  "name": "IP BAN",
  "items": [
    {
      "type": "IP_ADDRESS",
      "value": "203.0.113.10"
    }
  ]
}
```

Then create a UniFi firewall policy that blocks traffic from this list toward the protected reverse proxy or exposed service. UniFi Autoblock only updates the list; the firewall policy remains under your control.

## Auto-Detection

The following options can be left empty in simple installations:

- `unifi_site_id`
- `traffic_matching_list_id`
- `traffic_matching_list_name`

Auto-detection works when the controller has exactly one site and exactly one IPv4 address traffic matching list. If multiple sites or multiple IPv4 lists are found, the app stops and prints the available IDs in the logs so you can choose explicitly.

## UniFi Alarm Manager Setup

Start the app once and open its logs. It prints the setup values in this order:

```text
UniFi Alarm Manager webhook URL: http://<HOME_ASSISTANT_IP>:37989/webhook/...
Replace <HOME_ASSISTANT_IP> with the local Home Assistant IP address
UniFi Alarm Manager authentication: Bearer ...
Automatically accepted webhook source: 192.168.1.1/32
```

In UniFi Alarm Manager, create a webhook action with:

```text
Delivery method: POST
Delivery URL: http://HOME_ASSISTANT_IP:37989/webhook/TOKEN_FROM_LOGS
Authentication: Bearer
Bearer token: BEARER_TOKEN_FROM_LOGS
Content: Default Content
```

Replace `HOME_ASSISTANT_IP` with the local IP address of Home Assistant. The placeholder URL printed in the logs will not work as-is.

If you change the mapped host port in the Home Assistant app network settings, restart UniFi Autoblock and copy the new URL from the logs.

## Configuration Options

| Option | Required | Default | Description |
| --- | --- | --- | --- |
| `unifi_base_url` | Yes | none | Local UniFi controller URL. Must use HTTPS, for example `https://192.168.1.1`. The same host is also used as the only accepted webhook source. |
| `unifi_api_key` | Yes | none | Dedicated UniFi API key used to read and update the traffic matching list. |
| `verify_ssl` | Yes | `false` | Enable TLS certificate verification for the UniFi controller. Keep `false` for self-signed UniFi certificates. |
| `dry_run` | Yes | `true` | Validate events and log what would happen without writing to UniFi. |
| `unifi_site_id` | No | empty | Optional UniFi site UUID. Leave empty for auto-detection when the controller has exactly one site. |
| `traffic_matching_list_id` | No | empty | Optional existing UniFi traffic matching list UUID. Leave empty for auto-detection. |
| `traffic_matching_list_name` | No | empty | Optional existing UniFi traffic matching list name. Leave empty when exactly one IPv4 address list exists. |
| `allowed_destinations` | No | empty | Internal IPs of protected services, for example the reverse proxy IP. Empty accepts any destination IP from valid UniFi IDS/IPS events. |
| `allowed_destination_ports` | Yes | `443` | Protected service ports to accept from UniFi IDS/IPS events. This is `parameters.dpt`, the attacked service port, not the app webhook port. |
| `min_severity` | Yes | `0` | Ignore UniFi events below this severity. Keep `0` to accept all severities. |
| `ban_ttl_days` | Yes | `30` | Number of days before app-managed entries expire. Manual UniFi list entries are not expired by the app. |
| `allowlist_cidrs` | No | empty | Optional public CIDRs that must never be blocked. Local and non-public ranges are already ignored automatically. |
| `log_level` | Yes | `info` | App log verbosity: `debug`, `info`, `warning`, or `error`. |

Removed options such as `webhook_token`, `webhook_base_url`, `allowed_webhook_sources`, rate limiting, and maximum list size are no longer configurable. Webhook secrets and source filtering are handled automatically.

## Event Validation

An incoming webhook is processed only when all of these conditions match:

- `name` is `Threat Detected and Blocked`
- `parameters.act` is `blocked`
- `parameters.UNIFIdirection` is `incoming`
- `parameters.UNIFIpolicyType` is `IDS/IPS`
- `severity` is greater than or equal to `min_severity`
- `parameters.dst` matches `allowed_destinations`, unless that list is empty
- `parameters.dpt` matches `allowed_destination_ports`
- `parameters.src` is a public global IPv4 address
- `parameters.src` is not inside `allowlist_cidrs`

Ignored events return HTTP `202` and are logged with the reason.

## Expected Logs

Dry run mode:

```text
DRY RUN: would add 160.119.76.64 to IP BAN
```

Successful write:

```text
Saved UniFi traffic matching list backup before PUT: /data/last_traffic_matching_list_backup.json
Added 160.119.76.64 to IP BAN
```

Already present:

```text
IP 160.119.76.64 is already present in UniFi blocklist
```

Failures are logged as `Failed to process webhook` with the underlying exception, for example a UniFi API error or update verification failure.

## First Run

Keep `dry_run: true` first. Confirm that the app logs only public attacker IPs for the service IP and port you want to protect.

When the logs look correct, set:

```yaml
dry_run: false
```

The next valid event should add the source IP to the UniFi list.

## Health Check

```text
GET http://HOME_ASSISTANT_IP:37989/health
```

The health endpoint returns JSON with the app status and current dry-run state.
