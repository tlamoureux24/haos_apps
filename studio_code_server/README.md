# Studio Code Server + Codex

Experimental Home Assistant App providing a persistent development workspace
available exclusively through authenticated Home Assistant Ingress.

Its purpose is to provide remote access to an environment close to VS Code with
Git, SSH, Home Assistant tooling, and Codex from a computer or a phone connected
to the trusted home network or VPN.

## Experimental status

The `0.1.x` series validates real compatibility between code-server, Home
Assistant OS, and Codex. Do not use it as the only copy of an important Git
repository or SSH key.

Codex CLI is the supported reference interface. The official Codex IDE
extension is bundled for evaluation, but OpenAI does not explicitly document
code-server as a supported editor. The extension may fail to load or have
reduced functionality.

## Features

- code-server 4.132.0, available only through authenticated Ingress;
- `zsh` and `bash` integrated terminals;
- Git, OpenSSH client, Home Assistant CLI, Python, Node.js, rsync, and common tools;
- pinned Codex CLI 0.147.0 without requiring an OpenAI Platform API key;
- ChatGPT subscription sign-in through OAuth Device Code;
- bundled Codex, Home Assistant Config Helper, and YAML extensions;
- persistent editor settings, extensions, repositories, SSH keys, Git configuration, shell history, and Codex data;
- writable access to Home Assistant and App configuration.

## First start

1. Install and start the App.
2. Enable **Show in sidebar**.
3. Open **Code + Codex** from Home Assistant.
4. Create a terminal from the `Terminal` menu.
5. Run:

```bash
codex login --device-auth
```

6. Open the displayed address, sign in to ChatGPT, and enter the temporary code.
7. Verify the installation with `codex --version`, then run `codex`.

OAuth tokens are stored in private App storage. Never commit, paste, or share
the contents of `/data/home/.codex`.

## Git and SSH persistence

Configure Git identity once:

```bash
git config --global user.name "Your name"
git config --global user.email "you@example.com"
```

The App persists `/data/home/.gitconfig`, `/data/home/.ssh`,
`/data/home/.codex`, `/data/workspace`, and `/data/vscode`. The default private
workspace is included in cold App backups.

## Permissions and exposure

This is an administrative console. It has Supervisor `manager` access, the
Home Assistant API, writable configuration mounts, a root shell inside the
container, and outbound Internet access.

No direct network port is published. code-server internal authentication is
disabled because Home Assistant Ingress handles authentication and routing.
Never publish the internal port without adding separate authentication.

## Options

- `log_level`: startup log verbosity;
- `workspace_path`: initial folder, `/data/workspace` by default;
- `packages`: extra Debian packages installed on each start;
- `init_commands`: trusted root commands executed on each start.

## Origin

Derived from the MIT-licensed
[hassio-addons/addon-vscode](https://github.com/hassio-addons/addon-vscode).
See `LICENSE.upstream.md`, `THIRD_PARTY.md`, and `UPSTREAM.md`.
