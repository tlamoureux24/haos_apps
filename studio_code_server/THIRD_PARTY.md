# Third-party components

This Home Assistant App is derived from the MIT-licensed Home Assistant
Community Add-on **Studio Code Server**, originally created and maintained by
Franck Nijhof and its contributors:

- <https://github.com/hassio-addons/addon-vscode>
- upstream snapshot audited: `776ef9119524ff489345a6a60e13333264e67b1c`

The App downloads and packages pinned releases of:

- code-server: <https://github.com/coder/code-server>
- Codex CLI: <https://github.com/openai/codex>
- Home Assistant CLI: <https://github.com/home-assistant/cli>
- Codex IDE extension from the Microsoft Visual Studio Marketplace
- Home Assistant Config Helper and YAML extensions from Open VSX

The Home Assistant App `icon.png` and `logo.png` are resized, otherwise
unmodified copies of the official Visual Studio Code stable icon downloaded
from <https://code.visualstudio.com/brand>. Visual Studio Code, VS Code, and the
Visual Studio Code icon are trademarks of Microsoft Corporation. All rights
reserved. Their inclusion does not imply endorsement by Microsoft.

Each component remains governed by its own license and terms.
