FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache python3 py3-pip su-exec \
  && addgroup -S agent-gateway \
  && adduser -S -D -H -h /data -G agent-gateway -u 1000 agent-gateway

COPY requirements.txt /app/requirements.txt
RUN python3 -m pip install \
  --break-system-packages \
  --disable-pip-version-check \
  --no-cache-dir \
  --requirement /app/requirements.txt

COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations
COPY src /app/src
COPY run.sh /run.sh

RUN chmod 755 /run.sh

WORKDIR /app
CMD [ "/run.sh" ]
