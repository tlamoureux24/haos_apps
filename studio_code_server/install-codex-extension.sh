#!/usr/bin/env bash
set -euo pipefail

readonly CODEX_EXTENSION_VERSION="26.727.40816"
readonly EXTENSIONS_DIR="/data/vscode/extensions"

case "$(uname -m)" in
  x86_64) target_platform="linux-x64" ;;
  aarch64|arm64) target_platform="linux-arm64" ;;
  *)
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

tmpdir="$(mktemp -d)"
cleanup() {
  rm -rf "${tmpdir}"
}
trap cleanup EXIT

echo "Downloading the experimental Codex extension ${CODEX_EXTENSION_VERSION} for ${target_platform}..."
echo "The compressed download is about 200 MB and requires about 550 MB once installed."
curl --fail --location --retry 5 --compressed \
  --header "User-Agent: Mozilla/5.0" \
  --output "${tmpdir}/codex.vsix" \
  "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/openai/vsextensions/chatgpt/${CODEX_EXTENSION_VERSION}/vspackage?targetPlatform=${target_platform}"

mkdir -p "${EXTENSIONS_DIR}"
code-server \
  --extensions-dir "${EXTENSIONS_DIR}" \
  --install-extension "${tmpdir}/codex.vsix" \
  --force

echo "Codex extension installed. Reload the browser window to test it."
