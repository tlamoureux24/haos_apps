# Changelog

## 2.15.1-1

- Package the official Nginx Proxy Manager `2.15.1` image for Home Assistant.
- Persist the NPM database and configuration in `/data`.
- Persist `/etc/letsencrypt` as `/data/letsencrypt` across app updates and restarts.
- Expose the standard NPM ports 80, 81 and 443 without Home Assistant Ingress.
- Add bilingual English/French documentation and network labels.
- Add automatic stable upstream release detection, validation and version updates.
