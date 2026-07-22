# Changelog

## 0.107.78-1 - 2026-07-22

- Initial Home Assistant package based on the official AdGuard Home 0.107.78 image.
- Publish plain DNS and the setup interface by default.
- Make the official encrypted DNS, DNSCrypt and diagnostic ports optionally configurable.
- Keep the app on an isolated bridge network without Home Assistant Ingress or Supervisor APIs.
- Persist the official configuration and work directories in the app `addon_config` folder.
- Run AdGuard Home as the upstream `nobody` user with only the bind-service capability.
- Add bilingual documentation, official assets, AppArmor and automated upstream updates.
