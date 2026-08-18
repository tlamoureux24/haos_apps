# Changelog

## 0.1.11

- Update code-server to 4.133.0.
- Update Codex CLI to 0.147.0.
- Update Home Assistant CLI to 5.3.0.

## 0.1.10 - 2026-08-12

- Replace the custom Home Assistant App artwork with the official Visual Studio Code stable icon selected by the repository owner.
- Record the Microsoft source and trademark notice in the third-party documentation.

## 0.1.9 - 2026-08-12

- Remove the obsolete privileged-to-unprivileged terminal helper.
- Rename the remaining Codex launcher to `codex-wrapper.sh` to reflect its current role.
- Keep the same UID and Supervisor-credential isolation guarantees with fewer runtime files.

## 0.1.8 - 2026-08-12

- Add dedicated `icon.png` and `logo.png` assets for Home Assistant.
- Remove the obsolete command-line Codex extension downloader.
- Document installation of the official OpenAI Codex extension directly from the editor Marketplace.

## 0.1.7 - 2026-08-12

- Enable automatic Git remote fetching in code-server while keeping pulls manual.
- Add a protected App option for the private HA-MCP Streamable HTTP URL.
- Configure or update the `home-assistant` MCP server in persistent Codex settings at startup without logging its secret URL.
- Create the persistent Zsh startup file automatically to suppress the first-terminal setup wizard.

## 0.1.6 - 2026-08-12

- Run code-server itself, its extension host, all integrated terminals, and Codex as UID 1000.
- Remove Home Assistant Supervisor credentials from the entire interactive editor environment.
- Remove the root terminal profile; trusted root initialization remains available through App startup options.
- Migrate persisted editor extensions and settings to the unprivileged account.

## 0.1.5 - 2026-08-12

- Start Codex directly when invoked from the already-unprivileged default terminal.
- Retain the privilege drop when Codex is invoked deliberately from the root administrator profile.
- Test the complete default-terminal-to-Codex launch path in CI.

## 0.1.4 - 2026-08-12

- Give the unprivileged development user ownership of its persistent home directory.
- Fix Git lock-file creation for global configuration and future user-level tools.
- Exercise a real `git config --global` write in smoke tests.

## 0.1.3 - 2026-08-12

- Make an unprivileged `Codex workspace` shell the default integrated terminal.
- Keep a separate `Home Assistant Admin (root)` terminal profile for deliberate maintenance.
- Apply the safer profiles to existing editor settings without removing language packs or other preferences.

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
