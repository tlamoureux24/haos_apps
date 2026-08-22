# Changelog

## 1.3.2 - 2026-08-22

- Enforce the bounded AppArmor profile after the complete HAOS functional audit.
- Allow audited read access on transient `/mnt` CIFS trees used by rsync.
- Preserve the explicit capability set and user-configurable network, signal and mount operations required by SMB/CIFS and SMTP jobs.

## 1.3.1 - 2026-08-22

- Replace broad AppArmor file and executable-tree permissions with a bounded diagnostic baseline for S6, Lighttpd, CGI, cron, rsync, msmtp and CIFS helpers.
- Keep user-configurable network, signal and mount operations intentionally broad during this audit.
- Temporarily run the narrowed profile in complain mode for one complete HAOS functional campaign before the final enforced profile.

## 1.3.0 - 2026-08-22

- Redesign the complete Ingress interface with the shared Agent and UniFi visual language.
- Add the branded header, compact navigation, responsive metric cards and consistent light and dark themes.
- Replace Bootstrap tabs and modals with accessible native views and side drawers.
- Present rsync jobs with source-to-target summaries, schedules, latest states and transfer statistics.
- Reorganize SMTP settings and configuration transfers into focused responsive cards.
- Split the monolithic page into `index.html`, `assets/app.css` and `assets/app.js` without changing API or data contracts.
- Preserve French and English localization and every existing job, SMTP, import, export and log action.

## 1.2.0 - 2026-08-10

- Add complete French and English localization to the Ingress interface.
- Select English automatically for English-language browsers and keep French as the fallback.
- Add a persistent manual language selector alongside the light and dark theme controls.
- Localize forms, job states, validation, confirmations, imports, exports and runtime feedback.
- Format interface dates according to the selected language.

## 1.1.3 - 2026-07-19

- Restore `DAC_READ_SEARCH` in the Supervisor privilege set required by `mount.cifs`.
- Allow the precise `DAC_OVERRIDE`, `DAC_READ_SEARCH`, `SETPCAP` and `SYS_ADMIN` capability set in AppArmor.
- Fix CIFS jobs failing with `Unable to apply new capability set` after version 1.1.0.

## 1.1.2 - 2026-07-18

- Disable Home Assistant local-folder mappings by default.
- Keep `/share`, `/media` and `/backup` as documented manifest examples for users who need local rsync jobs.
- Avoid exposing writable Home Assistant folders for SMB/CIFS-only installations.

## 1.1.1 - 2026-07-18

- Update the Alpine rsync package from 3.4.3-r0 to 3.4.3-r1.

## 1.1.0 - 2026-07-18

- Rename and document the package consistently as a Home Assistant App.
- Remove the obsolete `codenotary` metadata.
- Add current Home Assistant metadata, OCI labels, cold backups and an internal watchdog.
- Add `aarch64` support alongside `amd64`.
- Explicitly map `/share`, `/media` and `/backup` without exposing Home Assistant configuration or other App data.
- Keep only the `SYS_ADMIN` privilege required for CIFS mounts.
- Tighten the AppArmor profile and private data permissions.
- Enable SMTP certificate verification.
- Remove the unused FastCGI package and stylesheet.
- Bundle Bootstrap 5.3.8 locally instead of loading assets from a public CDN.
- Add bilingual documentation, validation and automatic rsync package update detection.
