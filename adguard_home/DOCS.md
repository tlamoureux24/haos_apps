# AdGuard Home for Home Assistant

Languages / Langues: [Français](#francais) | [English](#english)

<a id="francais"></a>

## Français

Cette App est une enveloppe minimale autour de l'image Docker officielle
AdGuard Home. Elle fonctionne en réseau bridge, sans Ingress, sans API
Supervisor et avec une authentification AdGuard Home indépendante.

### Première configuration

1. Démarrez l'App.
2. Ouvrez `http://IP_LAN_HOME_ASSISTANT:3000`.
3. Conservez le port web `3000` et le port DNS `53`, sur toutes les interfaces.
4. Créez un identifiant administrateur unique et un mot de passe fort.
5. Configurez les résolveurs amont et les listes depuis AdGuard Home.

Ne publiez jamais le port d'administration sur Internet. Limitez-le au LAN et
au VPN par le pare-feu.

### Ports et DHCP

Le DNS `53/tcp+udp` et l'administration `3000/tcp` sont activés par défaut.
HTTP, HTTPS/DoH, DoH3, DoT, DoQ, DNSCrypt et le profilage sont disponibles mais
désactivés dans la configuration Réseau. Activez uniquement les protocoles
réellement configurés dans AdGuard Home.

DHCP n'est pas proposé : il nécessite les broadcasts de niveau 2 et
`host_network`, volontairement refusé par cette App. Conservez le DHCP sur le
routeur.

### HTTPS

Configurez d'abord HTTPS et le certificat dans AdGuard Home. Si son listener
HTTPS utilise ensuite le port interne 3000, activez **Raccourci web HTTPS** pour
que le bouton Home Assistant utilise `https://`. Cette option ne configure pas
TLS elle-même.

### Données et sécurité

La configuration et les données se trouvent dans le dossier `addon_config` de
l'App, sous `conf/` et `work/`. Les sauvegardes sont effectuées à froid et sont
sensibles. AdGuard Home s'exécute sans root et ne reçoit aucun token Home
Assistant.

Documentation française complète :
[README.fr.md](https://github.com/tlamoureux24/haos_apps/blob/main/adguard_home/README.fr.md)

Documentation officielle :
<https://adguard-dns.io/kb/adguard-home/getting-started/>

Projet officiel : <https://github.com/AdguardTeam/AdGuardHome>

---

<a id="english"></a>

## English

This app is a minimal package around the official AdGuard Home Docker image. It
uses bridge networking, no Ingress, no Supervisor API, and independent native
AdGuard Home authentication.

### Initial Setup

1. Start the app.
2. Open `http://HOME_ASSISTANT_LAN_IP:3000`.
3. Keep web port `3000` and DNS port `53` on all interfaces.
4. Create a unique administrator username and strong password.
5. Configure upstream resolvers and filters in AdGuard Home.

Never expose the administration port to the Internet. Restrict it to trusted
LAN and VPN clients with a firewall.

### Ports and DHCP

Plain DNS on `53/tcp+udp` and administration on `3000/tcp` are enabled by
default. HTTP, HTTPS/DoH, DoH3, DoT, DoQ, DNSCrypt and profiling ports are
available but disabled in Network settings. Enable only protocols actually
configured inside AdGuard Home.

DHCP is unavailable because it requires layer-2 broadcasts and `host_network`,
which this package deliberately refuses. Keep DHCP on the router.

### HTTPS

Configure native HTTPS and its certificate inside AdGuard Home first. If its
HTTPS listener then uses internal port 3000, enable **HTTPS web shortcut** so
the Home Assistant button uses `https://`. This option does not configure TLS.

### Data and Security

Configuration and data are stored in the app `addon_config` folder under
`conf/` and `work/`. Backups are cold and sensitive. AdGuard Home runs without
root and receives no Home Assistant token.

Complete English documentation:
[README.md](https://github.com/tlamoureux24/haos_apps/blob/main/adguard_home/README.md)

Official documentation:
<https://adguard-dns.io/kb/adguard-home/getting-started/>

Official project: <https://github.com/AdguardTeam/AdGuardHome>
