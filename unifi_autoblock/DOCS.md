# UniFi Autoblock Documentation

Langues / Languages: [Français](#francais) | [English](#english)

<a id="francais"></a>

## Français

UniFi Autoblock reçoit les webhooks UniFi Alarm Manager et ajoute les adresses IPv4 publiques attaquantes à une liste UniFi `IPV4_ADDRESSES` existante.

L'app ne crée pas de règles firewall. Créez manuellement une règle firewall UniFi qui bloque le trafic provenant de votre liste vers le reverse proxy ou le service exposé à protéger.

### Sécurité

- `dry_run` est activé par défaut.
- L'URL API UniFi doit utiliser HTTPS.
- La clé API UniFi est saisie comme mot de passe, chiffrée localement, puis le champ de configuration est vidé.
- La clé locale de déchiffrement est exclue des sauvegardes Home Assistant.
- Le token d'URL webhook et le token Bearer sont générés automatiquement.
- Les appels webhook ne sont acceptés que depuis le contrôleur UniFi configuré dans `unifi_base_url`.
- L'accès API Home Assistant Core sert uniquement à émettre l'événement local `unifi_autoblock_ip_banned` après un bannissement confirmé.
- L'accès API Supervisor sert uniquement à vider le champ clé API UniFi après chiffrement.
- Aucun mode host network, mode privilégié, accès Docker ou accès API d'authentification n'est demandé.

Après restauration d'une sauvegarde Home Assistant ou réinstallation sans la clé locale de déchiffrement, saisissez à nouveau la clé API UniFi dans la configuration de l'app.

### UniFi Alarm Manager

Démarrez l'app et copiez les valeurs affichées dans les logs :

```text
UniFi Alarm Manager webhook URL: http://<HOME_ASSISTANT_IP>:37989/webhook/...
Replace <HOME_ASSISTANT_IP> with the local Home Assistant IP address
UniFi Alarm Manager authentication: Bearer ...
Automatically accepted webhook source: 192.168.1.1/32
```

Dans UniFi Alarm Manager, configurez :

```text
Delivery method: POST
Delivery URL: http://HOME_ASSISTANT_IP:37989/webhook/TOKEN_FROM_LOGS
Authentication: Bearer
Bearer token: BEARER_TOKEN_FROM_LOGS
Content: Default Content
```

`HOME_ASSISTANT_IP` doit être remplacé par l'adresse IP locale de Home Assistant.

### Options principales

| Option | Description |
| --- | --- |
| `unifi_base_url` | URL HTTPS du contrôleur UniFi local, par exemple `https://192.168.1.1`. L'hôte est aussi utilisé comme seule source webhook acceptée. |
| `unifi_api_key` | Clé API UniFi dédiée. À saisir au premier setup ou après restauration depuis backup. L'app la chiffre localement et vide ce champ automatiquement. |
| `verify_ssl` | Active la vérification du certificat TLS UniFi. Garder `false` pour les certificats UniFi auto-signés. |
| `dry_run` | Valide les événements sans écrire dans UniFi. |
| `unifi_site_id` | UUID optionnel du site. Laisser vide pour détection automatique s'il n'existe qu'un seul site. |
| `traffic_matching_list_id` | UUID optionnel de la liste Traffic Matching UniFi. Laisser vide pour détection automatique. |
| `traffic_matching_list_name` | Nom optionnel de la liste Traffic Matching UniFi. Laisser vide si une seule liste IPv4 existe. |
| `allowed_destinations` | IP internes des services protégés. Vide accepte toute IP de destination dans les événements IDS/IPS valides. |
| `allowed_destination_ports` | Ports des services protégés dans les événements IDS/IPS, défaut `443`. Ce n'est pas le port webhook de l'app. |
| `min_severity` | Ignore les événements UniFi sous cette sévérité. Garder `0` pour tout accepter. |
| `ban_ttl_days` | Nombre de jours avant expiration des entrées gérées par l'app. Les entrées manuelles UniFi sont conservées. |
| `allowlist_cidrs` | CIDR publics optionnels à ne jamais bloquer. Les plages locales et non publiques sont ignorées automatiquement. |
| `log_level` | `debug`, `info`, `warning` ou `error`. |

### Règles de validation

L'app traite uniquement les événements où :

- `name` vaut `Threat Detected and Blocked`
- `parameters.act` vaut `blocked`
- `parameters.UNIFIdirection` vaut `incoming`
- `parameters.UNIFIpolicyType` vaut `IDS/IPS`
- l'IP et le port de destination correspondent aux filtres de service protégé
- la source est une adresse IPv4 publique globale

Les IPv6, IP privées, locales, loopback, link-local, multicast, réservées et allowlistées sont ignorées.

### Événement Home Assistant

Après l'ajout réussi d'une IP source dans UniFi, l'app émet l'événement local Home Assistant `unifi_autoblock_ip_banned`.

Champs utiles :

- `ip`
- `list_name`
- `expires_at`
- `destination`
- `destination_port`
- `severity`
- `signature`

Exemple de déclencheur d'automatisation :

```yaml
trigger:
  - platform: event
    event_type: unifi_autoblock_ip_banned
```

Utilisez `trigger.event.data.ip` dans votre message de notification pour inclure l'IP bannie.

### Documentation complète

Voir le [README français sur GitHub](https://github.com/tlamoureux24/haos_apps/blob/main/unifi_autoblock/README.fr.md) ou le [README anglais sur GitHub](https://github.com/tlamoureux24/haos_apps/blob/main/unifi_autoblock/README.md).

---

<a id="english"></a>

## English

UniFi Autoblock receives UniFi Alarm Manager webhook events and adds public IPv4 attacker addresses to an existing UniFi `IPV4_ADDRESSES` traffic matching list.

The app does not create firewall rules. Create a UniFi firewall policy manually that blocks traffic from your traffic matching list toward the protected reverse proxy or exposed service.

### Security

- `dry_run` is enabled by default.
- The UniFi API URL must use HTTPS.
- The UniFi API key is accepted as a password option, encrypted locally, and then the configuration field is cleared.
- The local decryption key is excluded from Home Assistant backups.
- The webhook URL token and Bearer token are generated automatically.
- Webhook calls are accepted only from the UniFi controller host configured in `unifi_base_url`.
- Home Assistant Core API access is used only to fire a local `unifi_autoblock_ip_banned` event after a confirmed ban.
- Supervisor API access is used only to clear the UniFi API key field after encryption.
- No host network, privileged mode, Docker access, or authentication API access is requested.

After restoring a Home Assistant backup or reinstalling the app without its local decryption key, enter the UniFi API key again in the app configuration.

### UniFi Alarm Manager

Start the app and copy the setup values from the logs:

```text
UniFi Alarm Manager webhook URL: http://<HOME_ASSISTANT_IP>:37989/webhook/...
Replace <HOME_ASSISTANT_IP> with the local Home Assistant IP address
UniFi Alarm Manager authentication: Bearer ...
Automatically accepted webhook source: 192.168.1.1/32
```

In UniFi Alarm Manager, configure:

```text
Delivery method: POST
Delivery URL: http://HOME_ASSISTANT_IP:37989/webhook/TOKEN_FROM_LOGS
Authentication: Bearer
Bearer token: BEARER_TOKEN_FROM_LOGS
Content: Default Content
```

`HOME_ASSISTANT_IP` must be replaced with the local IP address of Home Assistant.

### Main Options

| Option | Description |
| --- | --- |
| `unifi_base_url` | HTTPS URL of the local UniFi controller, for example `https://192.168.1.1`. The host is also used as the only accepted webhook source. |
| `unifi_api_key` | Dedicated UniFi API key. Enter it on first setup or after restoring from backup. The app encrypts it locally and clears this field automatically. |
| `verify_ssl` | Enable UniFi TLS certificate verification. Keep `false` for self-signed UniFi certificates. |
| `dry_run` | Validate events without writing to UniFi. |
| `unifi_site_id` | Optional site UUID. Leave empty for auto-detection when there is exactly one site. |
| `traffic_matching_list_id` | Optional UniFi traffic matching list UUID. Leave empty for auto-detection. |
| `traffic_matching_list_name` | Optional UniFi traffic matching list name. Leave empty when exactly one IPv4 list exists. |
| `allowed_destinations` | Internal IPs of protected services. Empty accepts any destination IP from valid IDS/IPS events. |
| `allowed_destination_ports` | Protected service ports from IDS/IPS events, default `443`. This is not the app webhook port. |
| `min_severity` | Ignore UniFi events below this severity. Keep `0` to accept all severities. |
| `ban_ttl_days` | Days before app-managed entries expire. Manual UniFi list entries are preserved. |
| `allowlist_cidrs` | Optional public CIDRs that must never be blocked. Local and non-public ranges are ignored automatically. |
| `log_level` | `debug`, `info`, `warning`, or `error`. |

### Validation Rules

The app only processes events where:

- `name` is `Threat Detected and Blocked`
- `parameters.act` is `blocked`
- `parameters.UNIFIdirection` is `incoming`
- `parameters.UNIFIpolicyType` is `IDS/IPS`
- the destination IP and port match the configured protected service filters
- the source is a public global IPv4 address

IPv6, private, local, loopback, link-local, multicast, reserved, and allowlisted source addresses are ignored.

### Home Assistant Event

After a source IP is successfully added to UniFi, the app fires the local Home Assistant event `unifi_autoblock_ip_banned`.

Useful event fields include:

- `ip`
- `list_name`
- `expires_at`
- `destination`
- `destination_port`
- `severity`
- `signature`

Example automation trigger:

```yaml
trigger:
  - platform: event
    event_type: unifi_autoblock_ip_banned
```

Use `trigger.event.data.ip` in your notification message to include the banned IP.

### Full README

See the [French README on GitHub](https://github.com/tlamoureux24/haos_apps/blob/main/unifi_autoblock/README.fr.md) or the [English README on GitHub](https://github.com/tlamoureux24/haos_apps/blob/main/unifi_autoblock/README.md).
