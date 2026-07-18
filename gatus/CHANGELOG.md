# Changelog

## 5.36.0-3 - 2026-07-18

- Make every SMS and SMTP option genuinely optional.
- Disable all alert providers in the initial configuration.
- Allow Gatus to start without any alert credentials.
- Validate SMTP port only when it is configured.

## 5.36.0-2 - 2026-07-18

- Simplify the initial Gatus configuration.
- Link to the official configuration documentation on the first line.
- Keep the Free Mobile SMS provider and sample endpoints fully commented.
- Remove the optional SQLite storage example from the initial file.

## 5.36.0-1 - 2026-07-18

- Package the official Gatus 5.36.0 binary as a Home Assistant app.
- Store the editable Gatus configuration in the dedicated addon_config folder.
- Keep Free Mobile SMS and SMTP values out of config.yaml by injecting private app options as environment variables.
- Run Gatus as an unprivileged user so ICMP checks work without NET_RAW on current Gatus releases.
- Generate a neutral initial configuration with no network endpoint.
- Add a custom AppArmor profile, cold backups, an internal watchdog and bilingual documentation.
- Add automated upstream release detection with deliberate Home Assistant updates.
