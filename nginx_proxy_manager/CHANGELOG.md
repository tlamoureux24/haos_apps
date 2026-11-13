# Changelog

## 2.17.0-2 - 2026-11-13

- Pin the rebuilt official Nginx Proxy Manager `2.17.0` image by its multi-architecture digest `sha256:91277490a919c792aa73b8d291af1ca84d32be74df988e543137976515763534`.
- Upstream republished the `2.17.0` tag on 2026-11-13 from the same source commit `5c8aec9b`, after rebuilding its `nginx-full` base image with a build-only fix (retry of the Lua SSL download).

## 2.17.0-1 - 2026-11-12

- Update the official Nginx Proxy Manager image from `2.16.0` to `2.17.0`.
- Pin the image by its multi-architecture digest `sha256:9cdfebbcbb6a70b84c538e6e39862c5d627171e5f4ea4bfda933f7643e3640a4`.
- Reset the Home Assistant package revision to `1`.

## 2.16.0-2 - 2026-11-07

- Pin the official Nginx Proxy Manager `2.16.0` image by its multi-architecture digest `sha256:4393e642e233e5efd5adeb7f10918d4aaea71c9ed875b94190273fc8e87f9594`.
- The upstream image content is unchanged.

## 2.16.0-1 - 2026-09-25

- Update the official Nginx Proxy Manager image from `2.15.1` to `2.16.0`.
- Reset the Home Assistant package revision to `1`.

## 2.15.1-2

- Remove the Home Assistant web UI shortcut because `[HOST]` can resolve to the
  external Home Assistant domain and expose a misleading port 81 URL.
- Keep NPM administration explicitly accessible through the Home Assistant LAN
  address or a trusted VPN only.
- Allow package-only revision increments while keeping the NPM version pinned.

## 2.15.1-1

- Package the official Nginx Proxy Manager `2.15.1` image for Home Assistant.
- Persist the NPM database and configuration in `/data`.
- Persist `/etc/letsencrypt` as `/data/letsencrypt` across app updates and restarts.
- Expose the standard NPM ports 80, 81 and 443 without Home Assistant Ingress.
- Add bilingual English/French documentation and network labels.
- Add automatic stable upstream release detection, validation and version updates.
- Validate the exact NPM API version and fresh-install setup state during CI smoke tests.
