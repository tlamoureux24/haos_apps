# Changelog

## 0.1.2 - 2026-08-12

- Run Codex and every child process as a dedicated unprivileged user.
- Remove the Home Assistant Supervisor token from the Codex runtime environment.
- Migrate persisted OAuth, SSH, Git, and workspace ownership automatically.
- Keep the administrative code-server terminal available for deliberate Home Assistant maintenance.

## 0.1.1 - 2026-08-12

- Move the 550 MB experimental Codex IDE extension out of the App image.
- Add `install-codex-extension` for an explicit, architecture-aware test after installation.
- Preserve the Codex CLI as the supported default and keep App construction independent from Microsoft Marketplace packaging behavior.

## 0.1.0 - 2026-08-12

- Create an experimental successor to the unmaintained Community Studio Code Server App.
- Update code-server to 4.132.0 and Home Assistant CLI to 5.3.0.
- Add the pinned Codex CLI 0.147.0 with persistent ChatGPT OAuth storage.
- Add a user-triggered installer to evaluate the official Codex IDE extension without making the large download part of App installation or startup.
- Bundle Home Assistant Config Helper and YAML support.
- Persist Git configuration, SSH keys, Codex data, terminal history, editor settings, extensions, and the default workspace in App private storage.
- Keep the service available exclusively through authenticated Home Assistant Ingress.
