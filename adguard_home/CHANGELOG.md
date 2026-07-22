# Changelog

## 0.107.78-5 - 2026-07-22

- Fixed restarts on Home Assistant systems that reject permission changes on
  the mounted `addon_config` directory roots.
- Preserved the existing unprivileged runtime and first-run ownership handover.

## 0.107.78-4 - 2026-07-22

- Normalize the setup wizard's default administration port from 80 to 3000
  before the unprivileged restart.
- Keep port 80 optional while making the default App and wizard configurations
  work together without manual intervention.

## 0.107.78-3 - 2026-07-22

- Transfer persistent ownership depth-first so restrictive `0700` parent
  directories remain traversable throughout the handover.
- Complete the first-run handover without granting `dac_override`; later
  starts leave the persistent ownership unchanged.

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
