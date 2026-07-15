FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache \
  ca-certificates \
  py3-cryptography \
  python3

COPY run.sh /
COPY unifi_autoblock.py /app/unifi_autoblock.py

RUN chmod 755 /run.sh

CMD [ "/run.sh" ]
