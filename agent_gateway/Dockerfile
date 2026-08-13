FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH
ARG BASE_IMAGE_DIGEST=unrecorded-local-build

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  org.opencontainers.image.base.name="ghcr.io/home-assistant/base:latest" \
  org.opencontainers.image.base.digest="${BASE_IMAGE_DIGEST}"

RUN apk add --no-cache python3 py3-pip py3-cryptography su-exec \
  && addgroup -S agent-gateway \
  && adduser -S -D -H -h /data -G agent-gateway -u 1000 agent-gateway

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install \
  --break-system-packages \
  --disable-pip-version-check \
  --no-cache-dir \
  --requirement /app/requirements.txt

COPY src /app/src
COPY logo.png /app/logo.png
COPY run.sh /run.sh

RUN chmod 755 /run.sh

WORKDIR /app
CMD [ "/run.sh" ]
