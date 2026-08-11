ARG BUILD_FROM="ghcr.io/openclaw/openclaw:2026.7.1"
FROM ${BUILD_FROM}

ARG OPENCLAW_VERSION="2026.7.1"
ARG BUILD_VERSION="2026.7.1-9"
ARG BUILD_ARCH
ARG TTYD_VERSION="1.7.7"

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  org.opencontainers.image.title="OpenClaw Home Assistant App" \
  org.opencontainers.image.description="Official OpenClaw gateway packaged as a Home Assistant app" \
  org.opencontainers.image.source="https://github.com/tlamoureux24/haos_apps" \
  org.opencontainers.image.version="${BUILD_VERSION}" \
  org.opencontainers.image.licenses="MIT"

USER root

# The launcher needs root briefly to prepare Home Assistant's persistent mount,
# then both OpenClaw and the HA-Ingress terminal run as the upstream node user.
RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates curl gosu \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Debian Bookworm does not package ttyd. Install the upstream static release,
# pinned by version and checksum for both Home Assistant architectures.
RUN case "${BUILD_ARCH}" in \
      amd64) ttyd_arch="x86_64"; ttyd_sha="8a217c968aba172e0dbf3f34447218dc015bc4d5e59bf51db2f2cd12b7be4f55" ;; \
      aarch64) ttyd_arch="aarch64"; ttyd_sha="b38acadd89d1d396a0f5649aa52c539edbad07f4bc7348b27b4f4b7219dd4165" ;; \
      *) echo "Unsupported BUILD_ARCH for ttyd: ${BUILD_ARCH}" >&2; exit 1 ;; \
    esac \
  && curl --fail --silent --show-error --location \
    "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.${ttyd_arch}" \
    --output /usr/local/bin/ttyd \
  && echo "${ttyd_sha}  /usr/local/bin/ttyd" | sha256sum --check --strict \
  && chmod 0755 /usr/local/bin/ttyd

COPY run.sh /usr/local/bin/ha-openclaw-entrypoint
COPY configure.py /usr/local/lib/ha-openclaw-configure.py
COPY oauth_device_login.py /usr/local/lib/ha-openclaw-oauth-device-login.py
COPY terminal.sh /usr/local/bin/ha-openclaw-shell

RUN chmod 755 \
  /usr/local/bin/ha-openclaw-entrypoint \
  /usr/local/bin/ha-openclaw-shell \
  /usr/local/lib/ha-openclaw-configure.py \
  /usr/local/lib/ha-openclaw-oauth-device-login.py

ENV OPENCLAW_UPSTREAM_VERSION="${OPENCLAW_VERSION}"

ENTRYPOINT ["tini", "-s", "--", "/usr/local/bin/ha-openclaw-entrypoint"]
