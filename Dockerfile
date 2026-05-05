ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM $BUILD_FROM

# Installation de rsync, cifs-utils (pour le montage) et des outils web
RUN apk add --no-cache \
    rsync \
    bash \
    lighttpd \
    fcgi \
    msmtp \
    cifs-utils \
    jq

# Copie des scripts et fichiers
COPY rootfs /

# Permissions
RUN chmod a+x /usr/local/bin/rsync_manager.sh && \
    chmod a+x /usr/local/bin/rsync_cron.sh && \
    chmod a+x /usr/local/bin/rsync_runner.sh && \
    chmod a+x /etc/services.d/*/run && \
    chmod a+x /etc/cont-init.d/*.sh &&\
    chmod a+x /www/cgi-bin/*.sh

# Port pour l'interface web
EXPOSE 8099
