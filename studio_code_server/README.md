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
extension can be installed separately for evaluation, but OpenAI does not explicitly document
code-server as a supported editor. The extension may fail to load or have
reduced functionality.

## Features

- code-server 4.132.0, available only through authenticated Ingress;
- `zsh` and `bash` integrated terminals;
- Git, OpenSSH client, Home Assistant CLI, Python, Node.js, rsync, and common tools;
- pinned Codex CLI 0.147.0 without requiring an OpenAI Platform API key;
- ChatGPT subscription sign-in through OAuth Device Code;
- bundled Home Assistant Config Helper and YAML extensions;
- optional manual installer for the experimental Codex extension;
- persistent editor settings, extensions, repositories, SSH keys, Git configuration, shell history, and Codex data;
- automatic remote Git fetching without automatic merges or pulls;
- optional HA-MCP setup through a protected App option;
- writable access to Home Assistant and App configuration.
- a dedicated unprivileged Codex runtime with no Supervisor token in its environment.

## First start

1. Install and start the App.
2. Enable **Show in sidebar**.
3. Open **Code + Codex** from Home Assistant.
4. Create a terminal from the `Terminal` menu. The editor and all its terminals
   use the unprivileged `codex` account.
5. Run:

```bash
codex login --device-auth
```

6. Open the displayed address, sign in to ChatGPT, and enter the temporary code.
7. Verify the installation with `codex --version`, then run `codex`.

OAuth tokens are stored in private App storage. Never commit, paste, or share
the contents of `/data/home/.codex`.

## Optional Codex extension experiment

Validate the CLI first. To deliberately test the editor-integrated Codex UI,
run `install-codex-extension` in the terminal and then reload the browser
window. The compressed download is about 200 MB and consumes about 550 MB in
persistent storage. It is kept out of the App build and startup path, and its
operation under code-server is not guaranteed.

## Git and SSH persistence

Configure Git identity once:

```bash
git config --global user.name "Your name"
git config --global user.email "you@example.com"
```

The App persists `/data/home/.gitconfig`, `/data/home/.ssh`,
`/data/home/.codex`, `/data/workspace`, and `/data/vscode`. The default private
workspace is included in cold App backups.

code-server periodically runs `git fetch` automatically so remote commits are
reported, but it never changes the local branch. Pulling remains deliberate.

## Home Assistant through HA-MCP

Copy the private Streamable HTTP URL displayed by the HA-MCP App into the
protected **Private HA-MCP URL** option, then restart this App. It automatically
configures a Codex server named `home-assistant`. The URL must end in
`/private_<secret>` and must never be committed or included in screenshots.

After restart, reload the editor window and ask Codex to check server
availability without executing a tool. Effective permissions are those exposed
by HA-MCP; starting read-only is recommended.

## Permissions and exposure

The startup container has Supervisor `manager` access, the Home Assistant API,
writable configuration mounts, and outbound Internet access.

code-server, its extension host, every terminal, and the `codex` command use the
dedicated `codex` account (UID 1000), with `SUPERVISOR_TOKEN` and `HASS_TOKEN`
removed from their environment. The normal workspace and persisted
OAuth/Git/SSH data are owned by that account. Extra packages and
`init_commands` run as root only during startup, before the interactive editor
is launched.

HAOS may still reject Linux `bubblewrap` isolation. Codex approvals remain in
effect, but they are not equivalent to an operating-system sandbox. Additional
Docker privileges are deliberately not granted to bypass that restriction.

No direct network port is published. code-server internal authentication is
disabled because Home Assistant Ingress handles authentication and routing.
Never publish the internal port without adding separate authentication.

## Options

- `log_level`: startup log verbosity;
- `workspace_path`: initial folder, `/data/workspace` by default;
- `ha_mcp_url`: optional private HA-MCP URL stored as a protected value;
- `packages`: extra Debian packages installed on each start;
- `init_commands`: trusted root commands executed on each start.

## Origin

Derived from the MIT-licensed
[hassio-addons/addon-vscode](https://github.com/hassio-addons/addon-vscode).
See `LICENSE.upstream.md`, `THIRD_PARTY.md`, and `UPSTREAM.md`.
