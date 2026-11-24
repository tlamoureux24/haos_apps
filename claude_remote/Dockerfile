FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH="amd64"
# Claude Code native musl binary from the official npm platform packages,
# pinned by version and by the SHA-512 of each registry tarball.
ARG CLAUDE_CODE_VERSION="2.1.331"
ARG CLAUDE_CODE_SHA512_AMD64="2d92d4e2f4e6ccd784c4b8bafa89bd1668a741ffcf78039eea5dd82e9d9c5284c0f88e7fb4050c7a857dc52903ce57aba1c1abcb82e27cca53ed03eb73e50e1c"
ARG CLAUDE_CODE_SHA512_AARCH64="01fd936435e122ac034f52a93e65d726fc87ec11e4d56681acaa7c1fb95bcdf30cb5459f944b9008a4ebb07aea1cae00562a5c322c92364a9f49a22c0c6b1031"

ENV BUILD_VERSION="${BUILD_VERSION}" \
    LANG="C.UTF-8"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apk add --no-cache \
        bash \
        ca-certificates \
        curl \
        jq \
        libgcc \
        libstdc++ \
        nginx \
        python3 \
        ripgrep \
        ttyd \
        util-linux-misc \
    && case "${BUILD_ARCH}" in \
         amd64) npm_arch="x64"; sha512="${CLAUDE_CODE_SHA512_AMD64}" ;; \
         aarch64) npm_arch="arm64"; sha512="${CLAUDE_CODE_SHA512_AARCH64}" ;; \
         *) echo "Unsupported architecture: ${BUILD_ARCH}" >&2; exit 1 ;; \
       esac \
    && curl --fail --silent --show-error --location --retry 5 \
        --output /tmp/claude-code.tgz \
        "https://registry.npmjs.org/@anthropic-ai/claude-code-linux-${npm_arch}-musl/-/claude-code-linux-${npm_arch}-musl-${CLAUDE_CODE_VERSION}.tgz" \
    && echo "${sha512}  /tmp/claude-code.tgz" | sha512sum -c - \
    && mkdir -p /tmp/claude-code /usr/share/licenses/claude-code \
    && tar -xzf /tmp/claude-code.tgz -C /tmp/claude-code \
    && install -m 0755 /tmp/claude-code/package/claude /usr/local/bin/claude \
    && install -m 0644 /tmp/claude-code/package/LICENSE.md /usr/share/licenses/claude-code/LICENSE.md \
    && addgroup -g 1000 claude \
    && adduser -D -u 1000 -G claude -h /data/home -s /bin/bash claude \
    && rm -rf /tmp/claude-code /tmp/claude-code.tgz

COPY managed-settings.json /etc/claude-code/managed-settings.json
COPY nginx.conf /etc/claude-remote/nginx.conf
COPY run.sh /usr/local/bin/claude-remote
COPY remote-control.sh /usr/local/bin/claude-remote-control
COPY claude-shell.sh /usr/local/bin/claude-shell
COPY claude-remote-setup.sh /usr/local/bin/claude-remote-setup
COPY ingress_ui.py ingress_ui.html /usr/local/lib/claude-remote/

RUN chmod 0755 \
        /usr/local/bin/claude-remote \
        /usr/local/bin/claude-remote-control \
        /usr/local/bin/claude-shell \
        /usr/local/bin/claude-remote-setup \
    && chmod 0644 /etc/claude-code/managed-settings.json \
    && /usr/local/bin/claude --version

HEALTHCHECK CMD curl --fail --silent http://127.0.0.1:8100/healthz >/dev/null || exit 1

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.title="Claude Remote Home Assistant App" \
    org.opencontainers.image.description="Claude Code Remote Control limited to the Home Assistant MCP server" \
    org.opencontainers.image.source="https://github.com/tlamoureux24/haos_apps"

CMD ["/usr/local/bin/claude-remote"]
