FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION="1.1.3"
ARG BUILD_ARCH

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.title="Rsync Manager Home Assistant App" \
    org.opencontainers.image.description="Schedule and monitor local or SMB/CIFS rsync jobs" \
    org.opencontainers.image.source="https://github.com/tlamoureux24/haos_apps" \
    org.opencontainers.image.version="${BUILD_VERSION}" \
    org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache \
    bash \
    ca-certificates \
    cifs-utils \
    jq \
    lighttpd \
    msmtp \
    rsync

COPY rootfs /

RUN chmod 755 \
    /usr/local/bin/rsync_manager.sh \
    /usr/local/bin/rsync_cron.sh \
    /usr/local/bin/rsync_runner.sh \
    /etc/services.d/*/run \
    /etc/cont-init.d/*.sh \
    /www/cgi-bin/*.sh

EXPOSE 8099
