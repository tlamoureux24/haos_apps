FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH="amd64"
# Claude Code native musl binary from the official npm platform packages,
# pinned by version and by the SHA-512 of each registry tarball.
ARG CLAUDE_CODE_VERSION="2.1.319"
ARG CLAUDE_CODE_SHA512_AMD64="2c08f4dd52d6599fb94f673774cc56661e41845cc4c70cb02294facb5a079c18f44f1fc82c85d8175cfa95c29262c9a2282862c4f5b3b28df942721f60b3bc8e"
ARG CLAUDE_CODE_SHA512_AARCH64="f7af6ab8fda75e3ec6447ccb49ef64a2ff5cfdfda9f99b99ad792bbda7a76cb397eb3649b72a992915328435236959921041854b1802aff06d50c39757c8da3b"

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
