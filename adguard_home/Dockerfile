ARG ADGUARD_HOME_VERSION="0.107.78"
FROM adguard/adguardhome:v${ADGUARD_HOME_VERSION}

ARG ADGUARD_HOME_VERSION
ARG BUILD_VERSION="0.107.78-6"
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  org.opencontainers.image.title="AdGuard Home Home Assistant App" \
  org.opencontainers.image.description="Official AdGuard Home packaged as a Home Assistant app" \
  org.opencontainers.image.source="https://github.com/tlamoureux24/haos_apps" \
  org.opencontainers.image.version="${BUILD_VERSION}" \
  org.opencontainers.image.licenses="GPL-3.0"

RUN apk add --no-cache su-exec

COPY run.sh /run.sh
RUN chmod 755 /run.sh

ENTRYPOINT ["/run.sh"]
CMD []
