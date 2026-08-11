# Upstream and maintenance policy

This App is derived from the MIT-licensed Home Assistant Community Add-on
[Studio Code Server](https://github.com/hassio-addons/addon-vscode). The
upstream project declared maintenance through 2025 and had not published a
release after 6.0.1 when this fork was created.

The original code was audited from commit
`776ef9119524ff489345a6a60e13333264e67b1c`. Its useful Home Assistant Ingress,
persistence, and environment integration patterns were retained, while the
runtime and dependency installation were rewritten for this repository.

Versions are pinned in `Dockerfile` and `upstream_versions`. Updates are never
installed inside a running container. A new App version must be built and
validated before Home Assistant offers it.

Open upstream pull requests are reviewed as references. They are not merged
blindly because changes to code-server, extensions, Ingress proxy handling, or
the base image can break startup or browser connectivity.
