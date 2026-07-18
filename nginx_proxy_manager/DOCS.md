# Nginx Proxy Manager for Home Assistant

Languages / Langues: [Français](#francais) | [English](#english)

<a id="francais"></a>

## Français

Cette App est une enveloppe minimale autour de l'image officielle Nginx Proxy
Manager. Elle expose les ports 80, 81 et 443, conserve les données NPM dans
`/data` et conserve `/etc/letsencrypt` dans `/data/letsencrypt`.

### Accès et sécurité

- Ne redirigez depuis Internet que les ports 80 et 443.
- Ne redirigez jamais le port d'administration 81 depuis Internet.
- Limitez le port 81 au LAN et au VPN avec votre pare-feu.
- Activez la double authentification de l'administrateur NPM.
- Choisissez **No Response (444)** comme site par défaut pour les hôtes inconnus.
- Les sauvegardes contiennent la base NPM, les identifiants et les clés privées.

### Home Assistant comme destination

Dans NPM, utilisez `http`, l'hôte `homeassistant`, le port `8123` et activez les
WebSockets. Dans Home Assistant, activez `use_x_forwarded_for` et configurez le
proxy immédiat dans `trusted_proxies`. L'exemple officiel HA pour les Apps est :

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 172.30.33.0/24
```

### Certificats

HTTP-01 convient à une IP fixe, sans wildcard, avec le port 80 public. DNS-01
convient aux wildcards ou lorsque le port 80 ne peut pas être exposé.

### Sauvegarde

La sauvegarde est effectuée à froid : Home Assistant arrête brièvement l'App,
copie `/data`, puis la redémarre afin de garantir la cohérence de SQLite.

Documentation française complète :
[README.fr.md](https://github.com/tlamoureux24/haos_apps/blob/main/nginx_proxy_manager/README.fr.md)

---

<a id="english"></a>

## English

This app is a minimal package around the official Nginx Proxy Manager image. It
exposes ports 80, 81 and 443, persists NPM data in `/data`, and persists
`/etc/letsencrypt` in `/data/letsencrypt`.

### Access and Security

- Forward only ports 80 and 443 from the Internet.
- Never forward administration port 81 from the Internet.
- Restrict port 81 to LAN and VPN clients with your firewall.
- Enable two-factor authentication for the NPM administrator.
- Select **No Response (444)** as the default site for unknown hosts.
- Backups contain the NPM database, credentials and certificate private keys.

### Home Assistant as a Target

In NPM, use `http`, hostname `homeassistant`, port `8123`, and enable WebSockets.
In Home Assistant, enable `use_x_forwarded_for` and add the immediate proxy to
`trusted_proxies`. The official HA app-network example is:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 172.30.33.0/24
```

### Certificates

HTTP-01 is suitable for a fixed IP without wildcards when public port 80 is
available. DNS-01 is suitable for wildcards or when port 80 cannot be exposed.

### Backup

Backups are cold: Home Assistant briefly stops the app, copies `/data`, and
restarts it to keep SQLite consistent.

Complete English documentation:
[README.md](https://github.com/tlamoureux24/haos_apps/blob/main/nginx_proxy_manager/README.md)
