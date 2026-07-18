# Rsync Manager

[Documentation française](README.fr.md)

Rsync Manager is a Home Assistant App for configuring, scheduling, testing and
monitoring `rsync` synchronizations from an authenticated Ingress interface.

It supports:

- local folder to local folder;
- local folder to SMB/CIFS share;
- SMB/CIFS share to local folder;
- SMB/CIFS share to another SMB/CIFS share.

## Installation

Add this repository to the Home Assistant App Store:

```text
https://github.com/tlamoureux24/haos_apps
```

Install `Rsync Manager`, start it, then open its Ingress interface. No port is
published on the LAN and Home Assistant handles authentication.

## Interface

The interface contains three tabs:

- `JOBS`: create, edit, schedule, test and run synchronization jobs;
- `SMTP`: configure optional email reports;
- `MANAGEMENT`: import or export jobs and email settings.

Each job has a stable identifier and can be enabled or disabled independently.
Disabling a job removes it from the generated cron schedule but does not block
manual runs.

## Sources and destinations

Each side of a job can use either a local path or an SMB/CIFS share.

### Local paths

The web interface supports local paths, but Home Assistant folder mappings are
intentionally disabled by default. SMB/CIFS-only installations therefore do
not expose writable host folders unnecessarily.

Repository owners who need local jobs can uncomment only the required entries
in `config.yaml`:

```yaml
map:
  - type: share
    read_only: false
  - type: media
    read_only: false
  - type: backup
    read_only: false
```

After changing the manifest, reload the App Store and rebuild or reinstall the
App. These mappings cannot be enabled dynamically from the App options because
the Supervisor creates them before the container starts.

Examples:

```text
/share/photos
/media/camera
/backup/archives
```

Only uncomment folders that are actually used. The Home Assistant
configuration, SSL certificates and other Apps' private configuration folders
must remain unexposed.

### SMB/CIFS shares

For an SMB/CIFS endpoint, configure:

- server address or hostname;
- share name;
- optional subfolder;
- username and password;
- optional domain or workgroup.

Rsync Manager uses SMB 3.0 with `ntlmssp`, `noserverino` and `nounix`. These
safe defaults are intentionally fixed in the interface. Credentials are passed
to `mount.cifs` through a temporary mode-`0600` file and are masked in logs.

The App needs `SYS_ADMIN` solely to mount and unmount CIFS shares. It does not
request `DAC_READ_SEARCH`, access to the Docker socket or either Home Assistant
API.

## Rsync behavior

Real jobs use:

```text
-a -v -h --delete
```

An SMB/CIFS destination additionally uses:

```text
--inplace --no-perms --no-owner --no-group --chmod=ugo=rwX
```

This avoids common ownership and Unix permission errors on SMB destinations.
The destination mirrors the source: files absent from the source are removed
from the destination because `--delete` is enabled.

Always use `Dry run` before the first real synchronization or after changing a
path or exclusion.

## Exclusions

Enter one rsync exclusion pattern per line. Examples:

```text
*.tmp
cache/
@eaDir/
lost+found/
```

The generated job-specific exclusion file is passed with `--exclude-from`.
Patterns are relative to the source root seen by rsync.

## Scheduling

Schedules use the standard five-field cron format:

```text
minute hour day-of-month month day-of-week
```

Examples:

```cron
0 3 * * *
30 2 * * 1
0 4 1 * *
```

They mean every day at 03:00, every Monday at 02:30, and the first day of every
month at 04:00 respectively. Saving, deleting or importing jobs regenerates the
container crontab.

## Tests, status and logs

Available job actions are:

- `Test mounts`: mounts both sides and verifies destination write access;
- `Dry run`: executes rsync without changing the destination;
- `Run`: executes the real synchronization;
- `View last log`: opens the persistent log for that job.

The interface reports the last start time, duration, trigger, result and rsync
transfer summary. Persistent state lives under `/data`:

```text
/data/jobs.json
/data/config.json
/data/status.json
/data/logs/<job_id>.log
```

These files are included in Home Assistant backups. The App uses cold backups
so it is stopped while its persistent data is copied.

## Email reports

SMTP notifications are optional. Automatic reports are sent only after real
manual or scheduled runs, not after dry runs or mount tests.

The interface supports SMTP authentication, TLS and STARTTLS. Server
certificates are verified against the system CA store. A server using a
self-signed or otherwise untrusted certificate is therefore rejected.

For Gmail, use port `587`, TLS and STARTTLS, and a Google application password.

## Secrets and exports

SMB and SMTP credentials are stored in the App's private `/data` volume with
mode `0600`. They are not part of `config.yaml`, are not published in this
repository and cannot be accessed through a Home Assistant mapped folder.

Home Assistant backups and browser exports do contain these credentials. Store
both securely. Imports and exports contain credentials in clear text by design.

## Updates

The App installs `rsync` from the Alpine repository used by the current Home
Assistant base image. A scheduled GitHub workflow builds that exact image and
checks the installed Alpine package version. When it changes, the workflow:

1. updates the recorded rsync package version;
2. increments the Home Assistant App version;
3. validates and builds the App;
4. smoke-tests its web interface;
5. commits the validated update.

Home Assistant then offers the new App version normally. Installation remains
manual unless the user explicitly enables automatic updates in Home Assistant.

## Troubleshooting

### A scheduled job does not run

Check that the job is enabled, its cron expression contains five fields and the
App log contains `[CRON]` messages.

### A mount test fails

Check the server, share, account permissions, destination write access and
network reachability from Home Assistant. The last job log contains the masked
CIFS options and full mount error.

### Rsync fails on an SMB destination

Inspect the last job log. Verify share permissions and the configured subfolder.
The App already applies its SMB compatibility profile automatically.

### Email delivery fails

Check the server, port, sender, recipient, authentication and TLS mode. The SMTP
server must present a certificate trusted by the system CA store.

## License

This Home Assistant App is distributed under the repository's MIT license.
Rsync and the other packaged components retain their respective licenses.
