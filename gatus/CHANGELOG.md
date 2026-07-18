# Changelog

## 5.36.0-1 - 2026-07-18

- Package the official Gatus 5.36.0 binary as a Home Assistant app.
- Store the editable Gatus configuration in the dedicated addon_config folder.
- Keep Free Mobile SMS and SMTP values out of config.yaml by injecting private app options as environment variables.
- Run Gatus as an unprivileged user so ICMP checks work without NET_RAW on current Gatus releases.
- Generate a neutral initial configuration with no network endpoint.
- Add a custom AppArmor profile, cold backups, an internal watchdog and bilingual documentation.
- Add automated upstream release detection with deliberate Home Assistant updates.
