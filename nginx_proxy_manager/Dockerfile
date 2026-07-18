ARG NPM_VERSION="2.15.1"
FROM docker.io/jc21/nginx-proxy-manager:${NPM_VERSION}

ARG BUILD_VERSION="2.15.1-1"
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  org.opencontainers.image.title="Nginx Proxy Manager for Home Assistant" \
  org.opencontainers.image.description="Official Nginx Proxy Manager packaged as a Home Assistant app" \
  org.opencontainers.image.source="https://github.com/tlamoureux24/haos_apps" \
  org.opencontainers.image.url="https://github.com/tlamoureux24/haos_apps/tree/main/nginx_proxy_manager" \
  org.opencontainers.image.licenses="MIT"

COPY entrypoint.sh /usr/local/bin/ha-npm-entrypoint

RUN chmod 755 /usr/local/bin/ha-npm-entrypoint \
  && rm -rf /etc/letsencrypt \
  && ln -s /data/letsencrypt /etc/letsencrypt

ENTRYPOINT [ "/usr/local/bin/ha-npm-entrypoint" ]
