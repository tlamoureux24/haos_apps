# Changelog

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
