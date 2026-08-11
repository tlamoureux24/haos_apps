ARG BUILD_FROM="ghcr.io/openclaw/openclaw:2026.7.1"
FROM ${BUILD_FROM}

ARG OPENCLAW_VERSION="2026.7.1"
ARG BUILD_VERSION="2026.7.1-1"
ARG BUILD_ARCH

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

# gosu is the only runtime addition. The launcher needs root briefly to prepare
# Home Assistant's persistent mount, then drops permanently to upstream's node
# user before OpenClaw starts.
RUN apt-get update \
  && apt-get install -y --no-install-recommends gosu \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

COPY run.sh /usr/local/bin/ha-openclaw-entrypoint
COPY configure.py /usr/local/lib/ha-openclaw-configure.py

RUN chmod 755 \
  /usr/local/bin/ha-openclaw-entrypoint \
  /usr/local/lib/ha-openclaw-configure.py

ENV OPENCLAW_UPSTREAM_VERSION="${OPENCLAW_VERSION}"

ENTRYPOINT ["tini", "-s", "--", "/usr/local/bin/ha-openclaw-entrypoint"]
