ARG BUILD_FROM="ghcr.io/hassio-addons/debian-base:9.3.0"
FROM ${BUILD_FROM}

ARG BUILD_ARCH="amd64"
ARG BUILD_VERSION="0.1.12"
ARG CODE_SERVER_VERSION="4.133.0"
ARG CODEX_VERSION="0.148.0"
ARG HA_CLI_VERSION="5.3.1"
ARG HOME_ASSISTANT_EXTENSION_VERSION="2.2.0"
ARG YAML_EXTENSION_VERSION="1.22.0"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ENV LANG="en_US.UTF-8" \
    LANGUAGE="en_US:en" \
    LC_ALL="en_US.UTF-8" \
    NPM_CONFIG_UPDATE_NOTIFIER="false"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash-completion \
        ca-certificates \
        curl \
        git \
        jq \
        less \
        locales \
        nano \
        nodejs \
        npm \
        openssh-client \
        procps \
        python3 \
        python3-venv \
        rsync \
        unzip \
        zsh \
    && sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && case "${BUILD_ARCH}" in \
         amd64) runtime_arch="amd64" ;; \
         aarch64) runtime_arch="arm64" ;; \
         *) echo "Unsupported architecture: ${BUILD_ARCH}" >&2; exit 1 ;; \
       esac \
    && curl --fail --location --retry 5 \
        --output /tmp/code-server.tar.gz \
        "https://github.com/coder/code-server/releases/download/v${CODE_SERVER_VERSION}/code-server-${CODE_SERVER_VERSION}-linux-${runtime_arch}.tar.gz" \
    && mkdir -p /usr/local/lib/code-server \
    && tar --extract --gzip --strip-components=1 \
        --file /tmp/code-server.tar.gz \
        --directory /usr/local/lib/code-server \
    && ln -s /usr/local/lib/code-server/bin/code-server /usr/local/bin/code-server \
    && npm install --global --omit=dev "@openai/codex@${CODEX_VERSION}" \
    && mv /usr/local/bin/codex /usr/local/bin/codex-real \
    && groupadd --gid 1000 codex \
    && useradd --uid 1000 --gid codex --home-dir /data/home --shell /bin/zsh codex \
    && curl --fail --location --retry 5 \
        --output /usr/local/bin/ha \
        "https://github.com/home-assistant/cli/releases/download/${HA_CLI_VERSION}/ha_${BUILD_ARCH}" \
    && chmod 0755 /usr/local/bin/ha \
    && mkdir -p \
        "/usr/local/lib/code-server/lib/vscode/extensions/keesschollaart.vscode-home-assistant-${HOME_ASSISTANT_EXTENSION_VERSION}" \
        "/usr/local/lib/code-server/lib/vscode/extensions/redhat.vscode-yaml-${YAML_EXTENSION_VERSION}" \
    && curl --fail --location --retry 5 \
        --output /tmp/home-assistant.vsix \
        "https://open-vsx.org/api/keesschollaart/vscode-home-assistant/${HOME_ASSISTANT_EXTENSION_VERSION}/file/keesschollaart.vscode-home-assistant-${HOME_ASSISTANT_EXTENSION_VERSION}.vsix" \
    && unzip -q /tmp/home-assistant.vsix 'extension/*' -d /tmp/home-assistant-extension \
    && cp -a /tmp/home-assistant-extension/extension/. \
        "/usr/local/lib/code-server/lib/vscode/extensions/keesschollaart.vscode-home-assistant-${HOME_ASSISTANT_EXTENSION_VERSION}/" \
    && curl --fail --location --retry 5 \
        --output /tmp/yaml.vsix \
        "https://open-vsx.org/api/redhat/vscode-yaml/${YAML_EXTENSION_VERSION}/file/redhat.vscode-yaml-${YAML_EXTENSION_VERSION}.vsix" \
    && unzip -q /tmp/yaml.vsix 'extension/*' -d /tmp/yaml-extension \
    && cp -a /tmp/yaml-extension/extension/. \
        "/usr/local/lib/code-server/lib/vscode/extensions/redhat.vscode-yaml-${YAML_EXTENSION_VERSION}/" \
    && rm -rf /tmp/* /root/.npm /var/lib/apt/lists/*

COPY run.sh /usr/local/bin/studio-code-server
COPY codex-wrapper.sh /usr/local/bin/codex
COPY settings.json /usr/local/share/studio-code-server/settings.json
COPY LICENSE.upstream.md /usr/share/licenses/studio-code-server/LICENSE.upstream.md
COPY THIRD_PARTY.md /usr/share/doc/studio-code-server/THIRD_PARTY.md

RUN chmod 0755 \
    /usr/local/bin/codex \
    /usr/local/bin/studio-code-server

HEALTHCHECK CMD curl --fail --silent http://127.0.0.1:1337/healthz >/dev/null || exit 1

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.title="Studio Code Server + Codex Home Assistant App" \
    org.opencontainers.image.description="Ingress-only development workspace with Git and Codex CLI" \
    org.opencontainers.image.source="https://github.com/tlamoureux24/haos_apps" \
    org.opencontainers.image.version="${BUILD_VERSION}" \
    org.opencontainers.image.licenses="MIT"

CMD ["/usr/local/bin/studio-code-server"]
