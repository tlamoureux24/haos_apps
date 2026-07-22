# Changelog

## 0.107.78-2 - 2026-07-22

- Keep the persistent directories owned by the temporary root process during
  the first-run wizard, then hand them to `nobody` before normal operation.
- Fix first-run startup under AppArmor without granting `dac_override`.

## 0.107.78-1 - 2026-07-22

- Initial Home Assistant package based on the official AdGuard Home 0.107.78 image.
- Publish plain DNS and the setup interface by default.
- Make the official encrypted DNS, DNSCrypt and diagnostic ports optionally configurable.
- Keep the app on an isolated bridge network without Home Assistant Ingress or Supervisor APIs.
- Persist the official configuration and work directories in the app `addon_config` folder.
- Run AdGuard Home as the upstream `nobody` user with only the bind-service capability.
- Add bilingual documentation, official assets, AppArmor and automated upstream updates.
