# Gatus for Home Assistant

[Documentation française](README.fr.md)

This App runs the official Gatus binary on Home Assistant OS or a supervised
installation. It does not modify Gatus and only adds the integration required
by Supervisor.

The App version follows the Gatus-version-package-revision format. The first
release is based on Gatus 5.36.0.

## Design

- official binary extracted from ghcr.io/twin/gatus;
- editable Gatus configuration in the dedicated addon_config folder;
- SMS and SMTP secrets stored in private App options;
- no secret in config.yaml or the GitHub repository;
- local web interface on port 8080;
- internal Supervisor watchdog;
- cold Home Assistant backups;
- custom AppArmor profile;
- no Home Assistant or Supervisor API access;
- no privileged mode, host networking or NET_RAW capability.

Since Gatus 5.31.0, ICMP checks support unprivileged pings when Gatus does not
run as root. The launcher reads the options and then executes the official
binary as the gatus user.

## Installation

Add this repository to the Home Assistant App store:

    https://github.com/tlamoureux24/haos_apps

Then install Gatus.

## First start

All alert options are optional. Enter only those used by the providers you
enable in config.yaml:

- sms_user;
- sms_password;
- email_from;
- email_username;
- email_password;
- email_host;
- email_port;
- email_to.

With no alert provider enabled, the App starts without any of these values.
In particular, leave email_port empty while the email provider is disabled.

On first start, the App automatically creates:

    /addon_configs/<repository_identifier>_gatus/config.yaml

The initial file is a valid skeleton with `endpoints: []` and contains no
address or name from your network. Add your checks through File editor, Studio
Code Server, Samba or SSH, depending on the tools installed.

Changes to config.yaml are reloaded automatically by Gatus. Changes to private
App options require an App restart because environment variables are injected
at startup.

## Secrets

The Gatus file only references these variables:

    ${GATUS_SMS_USER}
    ${GATUS_SMS_PASSWORD}
    ${GATUS_EMAIL_FROM}
    ${GATUS_EMAIL_USERNAME}
    ${GATUS_EMAIL_PASSWORD}
    ${GATUS_EMAIL_HOST}
    ${GATUS_EMAIL_PORT}
    ${GATUS_EMAIL_TO}

The launcher populates them from Supervisor options. They are never written to
addon_config, embedded in the image or printed to logs. Supervisor retains them
in private App data so they survive restarts and are included in backups.

## Access

The interface is available on the local network:

    http://HOME_ASSISTANT_IP:8080

The App intentionally declares neither Ingress nor a Web UI shortcut. Gatus
does not reliably support subpath publishing, and a Supervisor shortcut could
reuse Home Assistant's external hostname.

Port 8080 should remain restricted to the LAN or VPN unless it is deliberately
published behind a properly secured reverse proxy.

## Initial configuration

The supplied configuration:

- replaces deprecated disable-monitoring-lock with concurrency: 0;
- leaves every alert provider disabled;
- includes commented examples for email and the Free Mobile SMS API;
- provides no network endpoint by default.

The template is copied only when config.yaml does not exist. App updates never
overwrite the user's configuration.

## Optional persistent history

The previous deployment uses in-memory storage. To preserve history across
restarts, uncomment this section in config.yaml:

    storage:
      type: sqlite
      path: /data/gatus/gatus.db

The /data/gatus directory belongs to the unprivileged Gatus user and is included
in App backups.

## Availability limitation

This App monitors devices while the Home Assistant host is running. It cannot
send an alert when the Home Assistant machine itself is completely offline. Use
an external monitor if that coverage is required.

## Updates

A daily workflow detects new stable TwiN/gatus releases, verifies amd64 and
arm64 images, updates metadata, builds the App and runs a real startup and ICMP
smoke test.

The workflow commits the new version to the repository. Home Assistant then
offers the update, but does not install it automatically unless the user
explicitly enables automatic updates.

## Upstream

- Gatus: https://github.com/TwiN/gatus
- Gatus license: Apache-2.0
