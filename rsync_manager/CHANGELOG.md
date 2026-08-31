# Changelog

## 1.3.19 - 2026-08-31

- Update the Alpine rsync package from 3.4.3-r1 to 3.5.0-r0.

## 1.3.18 - 2026-08-23

- Enforce the consolidated AppArmor profile after a clean bounded startup, Ingress, cron, CIFS and rsync audit.
- Remove the temporary explicit `/mnt/**` audit modifier while retaining the validated recursive read/write/link/lock permissions required by rsync.
- Preserve the corrected S6 legacy-service inheritance and Alpine `/usr/sbin/mount.cifs` runtime path.

## 1.3.17 - 2026-08-23

- Complete the bounded complain trace with the resolved `/usr/sbin/mount.cifs` executable used by Alpine in addition to its `/sbin` alias.
- Allow enumeration of the `/proc/` root and creation of `/run/crond.pid`, the only direct-profile file accesses remaining after the S6 inheritance correction.
- Keep the profile in complain mode for one final short CIFS/Rsync validation capture.

## 1.3.16 - 2026-08-23

- Keep the AppArmor profile in complain mode while correcting the three actual S6 legacy-service entry points used by cron, runner and web.
- Prevent these longruns from falling into nested `//null-...` learning profiles, which made every descendant access appear as a separate missing permission.
- Preserve the complete runtime, CIFS and explicit `/mnt/**` audit baseline for one new bounded validation capture.

## 1.3.15 - 2026-08-23

- Replace implicit complain-violation collection with AppArmor's explicit rule-level audit mechanism for the bounded CIFS fixture.
- Restore recursive `/mnt/**` access as `audit /mnt/** rwlk,` so the small job remains fully authorized while every matching file access requests an audit record.
- Preserve the complete S6/runtime baseline and all application behavior unchanged.

## 1.3.14 - 2026-08-23

- Use the file-access audit path already proven by Rsync Manager's earlier HAOS complain trace.
- Keep the complete corrected S6/runtime baseline and normal `SYS_ADMIN` permission while deliberately omitting only recursive `/mnt/**` access.
- Bound the resulting AppArmor evidence with the small CIFS fixture instead of capability or SMTP witnesses.

## 1.3.13 - 2026-08-23

- End the diagnostic campaign with one explicit AppArmor audit witness for the required `SYS_ADMIN` capability.
- Restore authorization for CIFS mounts as `audit capability sys_admin,` so the bounded test remains functional while requesting an allowed-use audit record.
- Make this the final diagnostic release; retain the complete validated runtime baseline unchanged.

## 1.3.12 - 2026-08-23

- Replace the inconclusive SMTP execution witness with a bounded CIFS capability witness.
- Restore the explicit `msmtp` execution permission and deliberately omit only AppArmor `SYS_ADMIN` while remaining in complain mode.
- Require one small CIFS test job to distinguish complain enforcement, enforce behavior and missing audit delivery without changing the validated S6 baseline.

## 1.3.11 - 2026-08-23

- Add one bounded AppArmor complain-mode witness by deliberately omitting only the explicit `msmtp` execution permission.
- Keep the complete validated S6, cron, Ingress, CIFS and rsync baseline unchanged.
- Require one SMTP test to succeed while producing an AppArmor `ALLOWED` event, proving that HAOS loaded the diagnostic profile in complain mode before continuing the audit.

## 1.3.10 - 2026-08-23

- Start a consolidated AppArmor complain-mode audit using the complete audited HAOS S6 baseline and all Rsync Manager-specific startup fixes.
- Retain the disabled-cron-job correction from 1.3.9.
- Limit the production audit campaign to a deliberately small CIFS/Rsync fixture so file-level events remain bounded and analyzable.

## 1.3.9 - 2026-08-23

- Fix disabled jobs being included in the generated crontab because jq's `//` operator treats `false` as a fallback value.
- Normalize `enabled` as a strict boolean while preserving the historical enabled-by-default behavior for missing or invalid values.
- Refuse stale cron invocations for disabled jobs as a server-side safety check while keeping manual actions available.

## 1.3.8 - 2026-08-22

- Restore the complete AppArmor profile from version 1.3.0, immediately after the UI redesign.
- Restore the previously working enforcement baseline while a different, non-complain audit method is prepared for a future consolidated hardening pass.

## 1.3.7 - 2026-08-22

- Return the consolidated profile to complain mode for one clean post-reload startup audit.
- Stop iterative enforced releases and require aggregation of the complete startup trace before the next final enforcement.

## 1.3.6 - 2026-08-22

- Allow S6 to execute all three Rsync Manager longruns from their compiled dynamic service directories.
- Add both the command alias and resolved S6 2.15 executable for `s6-svwait`, used to await legacy service startup.

## 1.3.5 - 2026-08-22

- Allow complete generated-crontab access on Alpine's real `/etc/crontabs` target behind `/var/spool/cron/crontabs`.
- Cover cron file reading, creation, replacement, linking and locking as one rule set.

## 1.3.4 - 2026-08-22

- Replace the shortened S6 rules with the complete HAOS S6 runtime baseline already audited by the UniFi and Agent suites.
- Cover startup, service compilation, supervision and shutdown as one coherent block instead of adding permissions incrementally.

## 1.3.3 - 2026-08-22

- Allow S6 to enumerate its configuration roots while compiling the service database under the enforced AppArmor profile.
- Cover the exact S6, initialization, service and shutdown directories in addition to their existing contents.

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
