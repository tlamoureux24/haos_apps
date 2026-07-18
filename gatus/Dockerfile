ARG GATUS_VERSION="5.36.0"
FROM ghcr.io/twin/gatus:v${GATUS_VERSION} AS upstream

FROM ghcr.io/home-assistant/base:latest

ARG GATUS_VERSION
ARG BUILD_VERSION="5.36.0-2"
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  org.opencontainers.image.title="Gatus Home Assistant App" \
  org.opencontainers.image.description="Official Gatus packaged as a Home Assistant app" \
  org.opencontainers.image.source="https://github.com/tlamoureux24/haos_apps" \
  org.opencontainers.image.version="${BUILD_VERSION}" \
  org.opencontainers.image.licenses="Apache-2.0"

RUN apk add --no-cache su-exec \
  && addgroup -S gatus \
  && adduser -S -D -H -G gatus -s /sbin/nologin gatus

COPY --from=upstream /gatus /usr/local/bin/gatus
COPY run.sh /
COPY config.example.yaml /usr/share/gatus/config.example.yaml

RUN chmod 755 /run.sh /usr/local/bin/gatus

ENV GATUS_CONFIG_PATH="/config/config.yaml"
ENV GATUS_LOG_LEVEL="INFO"
ENV PORT="8080"

EXPOSE 8080

CMD ["/run.sh"]
