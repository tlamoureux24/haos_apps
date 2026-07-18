# Nginx Proxy Manager for Home Assistant

Documentation: [English](README.md) | [Français](README.fr.md)

This Home Assistant app is a deliberately thin package around the official
[Nginx Proxy Manager](https://github.com/NginxProxyManager/nginx-proxy-manager)
Docker image. It does not fork, patch, add to, or remove NPM features.

The app adds only what the Home Assistant Supervisor needs:

- Home Assistant app metadata and standard ports 80, 81 and 443;
- persistent NPM data under `/data`;
- persistent Let's Encrypt state under `/data/letsencrypt`;
- a cold-backup policy for consistent SQLite backups;
- automated tracking of stable upstream NPM releases.

The app version follows `<NPM version>-<package revision>`. For example,
`2.15.1-1` contains official NPM `2.15.1` and package revision `1`.

## Installation

Add this Home Assistant app repository:

```text
https://github.com/tlamoureux24/haos_apps
```

Then install **Nginx Proxy Manager** from the app store. The first build pulls
the pinned official NPM image and creates only the small Home Assistant wrapper
layer.

The app supports `amd64` and `aarch64`, matching current upstream NPM images.

## Network

| Container port | Default host port | Purpose |
| --- | ---: | --- |
| `80/tcp` | `80` | Public HTTP and Let's Encrypt HTTP-01 challenge |
| `81/tcp` | `81` | NPM administration interface |
| `443/tcp` | `443` | Public HTTPS |

Home Assistant publishes configured app ports on the host. The app cannot bind
port 81 to a specific LAN interface by itself. Enforce LAN/VPN-only access with
your router and firewall:

- forward WAN ports 80 and 443 only;
- never forward port 81 from the Internet;
- restrict port 81 to trusted LAN/VPN networks;
- keep NPM administrator two-factor authentication enabled.

This app intentionally does not use Home Assistant Ingress because the official
NPM frontend is not designed to run below an Ingress URL prefix.

The Home Assistant **Open Web UI** shortcut is intentionally disabled. The
Supervisor substitutes `[HOST]` with the Home Assistant URL currently in use,
which can produce an unsafe or unusable external-domain link to port 81. Open
NPM explicitly with its LAN address, for example `http://HOME_ASSISTANT_LAN_IP:81`,
or connect through a trusted VPN.

## Persistent Data and Backups

NPM normally uses two Docker volumes: `/data` and `/etc/letsencrypt`. Home
Assistant already persists `/data`, so this wrapper links `/etc/letsencrypt` to
`/data/letsencrypt`. The NPM SQLite database, proxy configuration, certificates,
private keys, renewal configuration and DNS challenge credentials are therefore
included in Home Assistant backups.

The app requests a **cold backup**: Supervisor stops it briefly while copying
its data, then restarts it. This keeps the SQLite database consistent.

Treat Home Assistant backups as sensitive because they contain NPM credentials
and certificate private keys.

## Initial NPM Setup

Open `http://HOME_ASSISTANT_IP:81`. NPM `2.13.0` and later use an initial setup
wizard instead of a shared default account. Create the administrator account and
enable NPM two-factor authentication.

For an unknown hostname, **No Response (444)** is the recommended default site.

## Proxying Home Assistant

Create a proxy host with:

- scheme: `http`;
- forward hostname: `homeassistant`;
- forward port: `8123` unless Home Assistant uses a custom port;
- WebSocket support enabled;
- the desired SSL certificate and **Force SSL** enabled.

Home Assistant must trust the immediate reverse proxy. Configure
`use_x_forwarded_for` and the narrowest correct `trusted_proxies` entry in
`configuration.yaml`. Home Assistant's official reverse-proxy example uses the
app network `172.30.33.0/24`, but an exact NPM app IP is preferable when it is
stable in your installation.

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 172.30.33.0/24
```

Do not add broad LAN ranges unless they are actually trusted reverse proxies.

## Certificates

For a fixed public IP, an ordinary hostname and no wildcard requirement,
HTTP-01 is the simplest choice and avoids storing a DNS provider API token.
Keep public port 80 forwarded to NPM for issuance and renewal.

Use DNS-01 when you need wildcard certificates, cannot expose port 80, or need
certificate issuance for internal-only names. DNS provider credentials stored
by NPM are persisted and included in Home Assistant backups.

## Migrating an Existing NPM Installation

Never start the old NPM container and this app simultaneously when both use the
same host ports.

Before migration, create a complete backup of the old NPM `data` and
`letsencrypt` volumes. This app does not automatically import external Docker
volumes. For a small installation, recreating the proxy hosts in the new app is
usually safer and simpler. Keep the old container stopped but intact until the
new proxy and certificate renewals have been validated.

## Automatic Updates

The repository checks the official GitHub latest-release API every day and can
also be checked manually from GitHub Actions. When a new stable semantic version
is available, the workflow:

1. verifies that the official Docker image exists for both `amd64` and `arm64`;
2. updates the pinned upstream version and resets the package revision to `1`;
3. validates version consistency, metadata, scripts and official assets;
4. builds the wrapper and starts NPM for an HTTP smoke test;
5. commits the validated update directly to the repository.

Home Assistant then shows the new app version as an available update. Installing
that update remains a voluntary action in Home Assistant.

The update workflow requests only `contents: write` for its short-lived GitHub
token. No external secret, personal access token, or repository-wide permission
change is normally required.

## Scope and Support

NPM functionality, proxy behavior, certificates and upstream security fixes are
provided by the official NPM image. This repository maintains only the Home
Assistant packaging and update automation.

- Upstream NPM: <https://github.com/NginxProxyManager/nginx-proxy-manager>
- Home Assistant wrapper: <https://github.com/tlamoureux24/haos_apps/tree/main/nginx_proxy_manager>

The official NPM icon and logo are reused unchanged; see
[UPSTREAM_ASSETS.md](UPSTREAM_ASSETS.md) for sources and checksums.
