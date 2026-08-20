# Changelog

## 0.1.2

- Align the Ingress administration container maximum width with Agent Control Plane at 1840 px.

## 0.1.1

- Align the generic s6-overlay AppArmor bootstrap rules with the HAOS-proven Agent Control Plane profile, including explicit directory traversal permissions.
- Clarify that the Docker executable inventory is evidence only and does not enforce or validate the HAOS AppArmor profile.

## 0.1.0

- Add the executable HAOS Lot 0 shell with isolated Ingress and standalone listeners.
- Add bilingual responsive light/dark administration views for Overview and Activity.
- Add generation-1 SQLite infrastructure and bounded persistent safe activity metadata.
- Add timestamped logging, unprivileged startup, AppArmor baseline, validation, tests, and CI.
