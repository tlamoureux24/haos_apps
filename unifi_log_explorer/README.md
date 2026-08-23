# UniFi Log Explorer

UniFi Log Explorer is a standalone Home Assistant App for collecting, retaining,
and locally exploring activity from a UniFi environment. It combines Traffic
Flows retrieved from the local UniFi Network API with events received through
Syslog/CEF.

The administration interface is available exclusively through Home Assistant
Ingress. Home Assistant authenticates the user; the App has no local account or
password, and its internal TCP port 8090 is not published on the LAN.

## Features

- periodic Traffic Flows collection from a local UniFi console;
- UDP Syslog/CEF receiver with a strict source-address allowlist;
- flow deduplication and periodic recovery of late UniFi publications;
- 24-hour overview of clients, services, destinations, and actions;
- searchable, filterable, and paginated Traffic Flows explorer;
- complete detail page for every archived flow;
- searchable and paginated CEF / Syslog explorer;
- persistent light and dark browser themes;
- automatic French or English interface selection with a persistent manual override;
- Settings page for API testing, diagnostic export, and a read-only Home
  Assistant configuration summary;
- Home Assistant-authenticated Ingress access and collection health monitoring;
- filtered CSV exports, a 24-hour activity chart, and confirmed maintenance tools;
- configurable age and record-count retention limits.

French documentation: [README.fr.md](README.fr.md).

## Requirements

- Home Assistant OS or Home Assistant Supervised;
- a UniFi Network console reachable over HTTPS from the App;
- a UniFi API key for Traffic Flows collection;
- a UDP port reachable from UniFi devices for Syslog/CEF;
- an authenticated Home Assistant user with administrator access.

## Installation

1. Add this repository to the Home Assistant App store.
2. Install **UniFi Log Explorer**.
3. Configure the options for the target network before starting the App.
4. Keep UDP `5514` published for Syslog/CEF reception.
5. Start the App and open its Ingress interface from Home Assistant.

## Configuration

| Option | Purpose |
| --- | --- |
| `allowed_source_ips` | Exact IPv4 or IPv6 addresses allowed to send Syslog/CEF datagrams. CIDR ranges are not accepted. |
| `retention_hours` | Retention period for events and Traffic Flows. |
| `max_records` | Maximum record limit enforced during storage maintenance. |
| `unifi_base_url` | Local HTTPS URL of the UniFi console or gateway. |
| `unifi_site_slug` | Internal UniFi site identifier, commonly `default`. |
| `unifi_api_key` | API key used to read Traffic Flows. |
| `verify_ssl` | Verify the console TLS certificate chain when enabled. |
| `unifi_certificate_sha256` | Required SHA-256 certificate fingerprint when `verify_ssl` is disabled. |
| `flow_collection_enabled` | Enable periodic Traffic Flows collection. |
| `flow_poll_interval_seconds` | Interval between fast collection cycles. |
| `flow_initial_backfill_minutes` | Requested depth of the initial import. |
| `log_level` | Application log verbosity. |

The configuration displayed on the web **Settings** page is read-only. Change
options in Home Assistant and restart the App to apply them.
For upgrade compatibility, an existing `session_timeout_minutes` value is
accepted and ignored; Home Assistant now owns the authenticated session.

## Configuring Syslog/CEF in UniFi

Enable log forwarding to a SIEM server in UniFi Network:

- use the address of the Home Assistant host;
- use the published UDP port for the Syslog/CEF receiver;
- select the event categories that should be forwarded;
- add every device that sends its own messages directly to
  `allowed_source_ips`.

Datagrams from any other source are rejected before parsing and are not stored.
Only their count is retained.

## Configuring the Traffic Flows API

Set the local HTTPS URL, site identifier, and a UniFi API key, then enable
`flow_collection_enabled`. After restart:

1. the key is encrypted in the App private volume;
2. its value is cleared from the Home Assistant options;
3. **Test connection** on the Settings page verifies API access without keeping
   the flow read by the test.

UniFi API keys may not provide fine-grained permissions. A key used for
read-only collection can therefore have broader rights than this App needs. The
key is never displayed, and its encryption key is excluded from backups. Enter
the API key again after restoring the App to another installation.

TLS verification is mandatory before the API key is sent. Use `verify_ssl: true`
when the certificate chain is trusted. For a self-generated UniFi certificate,
keep it disabled and configure `unifi_certificate_sha256`; an absent or changed
fingerprint refuses the connection before authentication. Obtain it locally with:

```sh
openssl s_client -connect 192.168.1.1:443 -servername 192.168.1.1 </dev/null 2>/dev/null | openssl x509 -noout -fingerprint -sha256
```

## Collection behavior

On the first start with collection enabled, the App imports an initial period.
It then:

- polls the newest result pages at the configured interval;
- limits fast collection to five pages per cycle;
- deduplicates flows using the stable identifier supplied by UniFi;
- reconciles the previous 24 hours every six hours to recover late publications;
- splits large windows to stay below the UniFi result cap.

The Traffic Flows endpoint used by the UniFi Network interface is not a
documented public API. A UniFi Network update may therefore require an App
adaptation.

## Web interface

- **Overview**: collection state, 24-hour volumes, and top clients, services,
  destinations, and actions. Cards open the corresponding filtered explorer.
- **Traffic Flows**: text, source, destination, service, direction, and period
  filters with pagination and full flow details.
- **CEF / Syslog**: search across retained events with type, source, and period
  filters, plus complete event details.
- **Settings**: appearance, API test, diagnostic export, and read-only
  configuration, storage health, and data maintenance.

## Storage and backups

Events and Traffic Flows are stored in SQLite inside the App private volume.
Periodic maintenance applies `retention_hours` and `max_records`.

The database is included in cold Home Assistant backups. The key used to encrypt
the UniFi API key is intentionally excluded. Diagnostic exports contain neither
complete Traffic Flows nor the API key, and omit sender addresses from the
recent-event section.

## Network security

- access administration only through Home Assistant Ingress;
- keep UDP `5514` limited to the networks that need to send Syslog/CEF;
- restrict the App network access to the UniFi console where possible;
- rotate the API key whenever its confidentiality is uncertain.
- update the pinned SHA-256 fingerprint only after independently verifying an intentional UniFi certificate renewal.

## Known limitations

- administration requires an authenticated Home Assistant administrator;
- UDP Syslog/CEF cannot guarantee delivery of every message;
- UniFi API keys can have broader permissions than the required read access;
- the internal Traffic Flows endpoint can change without notice;
- the App is a local exploration tool, not a complete SIEM or alerting engine.
