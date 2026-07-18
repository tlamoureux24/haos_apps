# UniFi Autoblock

Documentation : [Français](README.fr.md) | [English](README.md)

UniFi Autoblock est une app Home Assistant qui reçoit les webhooks locaux d'UniFi Alarm Manager et met à jour une liste UniFi `IPV4_ADDRESSES` existante avec les adresses IP sources des attaquants.

L'app est conçue pour une installation 100 % locale avec les clés API UniFi Network. Elle ne crée pas de règle firewall elle-même ; elle met uniquement à jour la liste d'IP utilisée par votre règle firewall UniFi existante.

## Fonctionnement

1. L'IDS/IPS UniFi détecte et bloque une menace entrante.
2. UniFi Alarm Manager envoie le payload webhook par défaut à UniFi Autoblock.
3. UniFi Autoblock vérifie le token d'URL webhook, le token Bearer et l'IP source du webhook.
4. L'app valide les champs de l'événement UniFi.
5. L'app accepte uniquement les adresses IPv4 publiques globales depuis `parameters.src`.
6. L'app lit la liste UniFi Traffic Matching configurée.
7. L'app sauvegarde la liste JSON actuelle dans `/data/last_traffic_matching_list_backup.json` avant chaque écriture.
8. Si l'IP attaquante n'est pas déjà présente, l'app l'ajoute à la liste UniFi et vérifie la mise à jour.
9. Les entrées gérées par l'app expirent après le TTL configuré.

Les entrées manuelles existantes sont conservées. Le nettoyage TTL ne s'applique qu'aux IP ajoutées par UniFi Autoblock et suivies dans `/data/state.json`.

Les IPv6, IP privées, loopback, link-local, multicast, réservées et autres adresses non publiques sont ignorées automatiquement. Les alertes IDS/IPS internes ne doivent donc pas ajouter vos appareils locaux à la blocklist.

## Modèle de sécurité

- `dry_run` est activé par défaut.
- `unifi_base_url` doit utiliser `https://`; le HTTP non chiffré est refusé pour protéger la clé API UniFi en transit.
- `verify_ssl: false` est supporté pour les certificats UniFi auto-signés, mais la connexion reste chiffrée en HTTPS.
- La clé API UniFi est saisie comme option de type mot de passe, chiffrée dans `/data/unifi_api_key.enc`, puis le champ de configuration est vidé.
- La clé locale de déchiffrement est stockée dans `/data/unifi_api_key.key` et exclue des sauvegardes Home Assistant.
- Le token d'URL webhook est généré automatiquement et stocké dans `/data/state.json`.
- Le token Bearer UniFi Alarm Manager est généré automatiquement et stocké dans `/data/state.json`.
- Les appels webhook ne sont acceptés que depuis l'hôte résolu depuis `unifi_base_url`, par exemple `https://192.168.1.1` devient `192.168.1.1/32`.
- L'accès à l'API Home Assistant Core sert uniquement à émettre l'événement local `unifi_autoblock_ip_banned` après un bannissement confirmé.
- L'accès à l'API Supervisor sert uniquement à vider le champ clé API UniFi après chiffrement.
- Aucun mode host network n'est demandé.
- Aucun mode privilégié n'est demandé.
- Seul `/data` est utilisé pour l'état de l'app.

Après restauration d'une sauvegarde Home Assistant ou réinstallation sans la clé locale de déchiffrement, saisissez à nouveau la clé API UniFi dans la configuration de l'app.

## Configuration UniFi requise

Créez ou réutilisez une liste d'adresses IPv4 dans UniFi. Exemple de forme API :

```json
{
  "type": "IPV4_ADDRESSES",
  "id": "00000000-0000-0000-0000-000000000000",
  "name": "IP BAN",
  "items": [
    {
      "type": "IP_ADDRESS",
      "value": "203.0.113.10"
    }
  ]
}
```

Créez ensuite une règle firewall UniFi qui bloque le trafic provenant de cette liste vers le reverse proxy ou le service exposé à protéger. UniFi Autoblock met uniquement la liste à jour ; la règle firewall reste sous votre contrôle.

## Détection automatique

Les options suivantes peuvent rester vides dans les installations simples :

- `unifi_site_id`
- `traffic_matching_list_id`
- `traffic_matching_list_name`

La détection automatique fonctionne lorsque le contrôleur possède exactement un site et exactement une liste Traffic Matching IPv4. Si plusieurs sites ou plusieurs listes IPv4 sont trouvés, l'app s'arrête et affiche les IDs disponibles dans les logs afin que vous puissiez choisir explicitement.

## Configuration UniFi Alarm Manager

Démarrez l'app une fois et ouvrez ses logs. Elle affiche les valeurs de configuration dans cet ordre :

```text
UniFi Alarm Manager webhook URL: http://<HOME_ASSISTANT_IP>:37989/webhook/...
Replace <HOME_ASSISTANT_IP> with the local Home Assistant IP address
UniFi Alarm Manager authentication: Bearer ...
Automatically accepted webhook source: 192.168.1.1/32
```

Dans UniFi Alarm Manager, créez une action webhook avec :

```text
Delivery method: POST
Delivery URL: http://HOME_ASSISTANT_IP:37989/webhook/TOKEN_FROM_LOGS
Authentication: Bearer
Bearer token: BEARER_TOKEN_FROM_LOGS
Content: Default Content
```

Remplacez `HOME_ASSISTANT_IP` par l'adresse IP locale de Home Assistant. L'URL affichée dans les logs avec le placeholder ne fonctionnera pas telle quelle.

Si vous changez le port hôte mappé dans les paramètres réseau de l'app Home Assistant, redémarrez UniFi Autoblock et copiez la nouvelle URL depuis les logs.

## Options de configuration

| Option | Obligatoire | Défaut | Description |
| --- | --- | --- | --- |
| `unifi_base_url` | Oui, pour démarrer | vide | URL locale du contrôleur UniFi. HTTPS obligatoire, par exemple `https://192.168.1.1`. Le même hôte est aussi utilisé comme seule source webhook acceptée. Le champ peut être vide uniquement au premier setup ou après reset des valeurs par défaut. |
| `unifi_api_key` | Oui, pour démarrer | vide | Clé API UniFi dédiée utilisée pour lire et mettre à jour la liste Traffic Matching. À saisir au premier setup ou après restauration depuis backup. L'app la chiffre localement puis vide ce champ automatiquement. |
| `verify_ssl` | Oui | `false` | Active la vérification du certificat TLS du contrôleur UniFi. Garder `false` pour les certificats UniFi auto-signés. |
| `dry_run` | Oui | `true` | Valide les événements et journalise ce qui serait fait sans écrire dans UniFi. |
| `unifi_site_id` | Non | vide | UUID optionnel du site UniFi. Laisser vide pour détection automatique si le contrôleur n'a qu'un seul site. |
| `traffic_matching_list_id` | Non | vide | UUID optionnel de la liste Traffic Matching UniFi existante. Laisser vide pour détection automatique. |
| `traffic_matching_list_name` | Non | vide | Nom optionnel de la liste Traffic Matching UniFi existante. Laisser vide si une seule liste IPv4 existe. |
| `allowed_destinations` | Non | vide | IP internes des services protégés, par exemple l'IP du reverse proxy. Vide accepte toute IP de destination depuis les événements IDS/IPS UniFi valides. |
| `allowed_destination_ports` | Oui | `443` | Ports des services protégés à accepter dans les événements IDS/IPS UniFi. Il s'agit de `parameters.dpt`, le port attaqué, pas le port webhook de l'app. Plusieurs ports peuvent être saisis, par exemple `80` et `443`. |
| `min_severity` | Oui | `0` | Ignore les événements UniFi sous cette sévérité. Garder `0` pour tout accepter. |
| `ban_ttl_days` | Oui | `30` | Nombre de jours avant expiration des entrées gérées par l'app. Les entrées manuelles UniFi ne sont pas expirées par l'app. |
| `allowlist_cidrs` | Non | vide | CIDR publics optionnels à ne jamais bloquer. Les plages locales et non publiques sont déjà ignorées automatiquement. |
| `log_level` | Oui | `info` | Verbosité des logs : `debug`, `info`, `warning` ou `error`. |

## Validation des événements

Un webhook entrant est traité uniquement lorsque toutes ces conditions correspondent :

- `name` vaut `Threat Detected and Blocked`
- `parameters.act` vaut `blocked`
- `parameters.UNIFIdirection` vaut `incoming`
- `parameters.UNIFIpolicyType` vaut `IDS/IPS`
- `severity` est supérieur ou égal à `min_severity`
- `parameters.dst` correspond à `allowed_destinations`, sauf si cette liste est vide
- `parameters.dpt` correspond à `allowed_destination_ports`
- `parameters.src` est une adresse IPv4 publique globale
- `parameters.src` n'est pas dans `allowlist_cidrs`

Les événements ignorés retournent HTTP `202` et sont journalisés avec la raison.

## Événement Home Assistant

Après l'ajout réussi d'une IP source dans UniFi, l'app émet cet événement Home Assistant local :

```text
unifi_autoblock_ip_banned
```

Les données de l'événement incluent `ip`, `list_name`, `list_id`, `site_id`, `expires_at`, `ttl_days`, `destination`, `destination_port`, `severity`, `protocol`, `signature`, `region`, `event_time`, `alarm_id` et `expired_removed`.

Exemple de déclencheur d'automatisation :

```yaml
trigger:
  - platform: event
    event_type: unifi_autoblock_ip_banned
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "UniFi Autoblock"
      message: "IP bannie : {{ trigger.event.data.ip }}"
```

## Logs attendus

Mode simulation :

```text
DRY RUN: would add 160.119.76.64 to IP BAN
```

Écriture réussie :

```text
Saved UniFi traffic matching list backup before PUT: /data/last_traffic_matching_list_backup.json
Added 160.119.76.64 to IP BAN
Fired Home Assistant event unifi_autoblock_ip_banned
```

IP déjà présente :

```text
IP 160.119.76.64 is already present in UniFi blocklist
```

Les échecs sont journalisés avec `Failed to process webhook` et l'exception sous-jacente, par exemple une erreur API UniFi ou un échec de vérification après mise à jour.

## Premier démarrage

Gardez d'abord `dry_run: true`. Vérifiez que l'app journalise uniquement des IP publiques attaquantes pour l'IP et le port du service que vous souhaitez protéger.

Lorsque les logs sont corrects, passez :

```yaml
dry_run: false
```

Le prochain événement valide doit ajouter l'IP source à la liste UniFi.

## Health Check

```text
GET http://HOME_ASSISTANT_IP:37989/health
```

Le endpoint health retourne du JSON avec l'état de l'app et l'état actuel du mode simulation.
