# TLS — Guide d’exploitation / Operations Guide

Le support TLS est officiellement disponible dans **Agent Control Plane (ACP)**,
**Agent Execution Plane (AEP)** et **MCP Capability Bridge**. Ce document est la
référence commune pour leur configuration et leur exploitation.

The TLS support of **Agent Control Plane (ACP)**, **Agent Execution Plane
(AEP)**, and **MCP Capability Bridge** is officially supported. This document is
the common configuration and operations reference.

---

## Français

### Périmètre et valeurs par défaut

TLS protège les surfaces publiques des Apps. L’administration reste
obligatoirement accessible par Home Assistant Ingress sur le port interne
`8099`; sa sécurité appartient à HAOS et ne se configure pas dans ces Apps.

| App | Surface publique | Port interne | Valeur par défaut |
|---|---|---:|---|
| ACP | API de réception des événements, `/api/v1/events` | `8100` | HTTP |
| ACP | Endpoint MCP/worker, `/mcp` | `8098` | HTTPS autogénéré |
| AEP | API autonome | `8098` | HTTPS autogénéré |
| MCP Bridge | Endpoint MCP, `/mcp` | `8098` | HTTPS autogénéré |

Les deux surfaces ACP sont indépendantes afin de conserver la compatibilité
avec les producteurs d’événements ne sachant utiliser que HTTP. Elles utilisent
cependant le même certificat lorsqu’elles sont toutes deux en HTTPS. Les ports
hôte sont choisis dans la section **Réseau** de l’App Home Assistant.

Pour chaque surface publique, l’administrateur choisit :

- `http` : compatible mais non chiffré; un avertissement explicite est écrit
  dans les logs et affiché dans **Transport & TLS**;
- `https` avec `self_generated` : l’App crée et conserve son certificat, et les
  partenaires vérifient son empreinte SHA-256;
- `https` avec `external` : l’administrateur fournit le certificat et la clé,
  renouvelle le certificat et s’assure que les clients font confiance à sa CA.

Les serveurs externes sans TLS, notamment HA-MCP, restent utilisables via une
URL `http://`. Cette décision est volontaire et signalée comme non chiffrée.

### Certificat autogénéré

Le certificat et sa clé sont créés sous `/data/private/tls`, persistent après
un redémarrage et sont inclus dans la sauvegarde des données de l’App. Le
certificat est valable cinq ans. Son empreinte SHA-256 et sa date d’expiration
sont affichées dans **Transport & TLS** et écrites dans les logs en anglais.

Le bouton **Régénérer le certificat** demande confirmation. La régénération
prend effet après le redémarrage de l’App et change normalement l’empreinte. Il
n’existe pas de période à deux empreintes : chaque partenaire doit être mis à
jour avec la nouvelle empreinte, vérifiée par un canal indépendant.

### Certificat externe et répertoire `/ssl`

Placez le certificat et la clé dans le partage Home Assistant `/ssl`. Dans les
options de l’App, saisissez **uniquement le nom relatif au partage** :

```yaml
certificate_source: external
certfile: agent-suite-cert.pem
keyfile: agent-suite-key.pem
```

Ainsi, `agent-suite-cert.pem` désigne `/ssl/agent-suite-cert.pem` dans le
conteneur. N’écrivez pas `/ssl/agent-suite-cert.pem`. Un chemin relatif vers un
sous-répertoire de `/ssl` est accepté; les chemins absolus, les traversées `..`
hors de `/ssl` et toute résolution externe sont refusés. Le montage `/ssl` est
en lecture seule.

Permissions recommandées et validées sur HAOS :

```sh
chmod 644 /ssl/agent-suite-cert.pem
chmod 600 /ssl/agent-suite-key.pem
```

Au démarrage, le bootstrap privilégié lit la clé depuis `/ssl`, la conserve
uniquement en mémoire, puis abandonne définitivement ses privilèges au profit
de l’UID/GID `1000`. La clé n’est ni copiée ni placée dans un répertoire
intermédiaire. Les fichiers `/ssl` doivent être sauvegardés séparément : ils ne
font pas partie des données privées de l’App.

Le certificat doit être en PEM, actuellement valide, porter
`basicConstraints CA:FALSE`, correspondre à la clé privée et convenir à un
serveur TLS. Pour la validation CA normale, son SAN doit contenir le nom DNS ou
l’adresse IP réellement utilisé par les clients. La clé doit être en PEM et
non chiffrée; les Apps ne demandent pas de mot de passe de clé au démarrage.
`certfile` peut contenir la chaîne serveur complète (feuille puis
intermédiaires).

### Générer un certificat serveur autosigné avec OpenSSL

Cet exemple crée un certificat utilisable par les Apps. Adaptez le DNS et
l’adresse IP avant de l’exécuter :

```sh
openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
  -keyout /ssl/agent-suite-key.pem \
  -out /ssl/agent-suite-cert.pem \
  -subj "/CN=agent-suite.local" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth" \
  -addext "subjectAltName=DNS:agent-suite.local,IP:192.168.1.58"
chmod 600 /ssl/agent-suite-key.pem
chmod 644 /ssl/agent-suite-cert.pem
```

Comme il est autosigné, les partenaires doivent utiliser son empreinte
SHA-256, sauf si ce certificat est ajouté explicitement à leur magasin de
confiance. Pour un certificat reconnu normalement, générez une CSR avec le même
SAN et faites-la signer par votre CA interne ou publique :

```sh
openssl req -new -newkey rsa:2048 -sha256 -nodes \
  -keyout /ssl/agent-suite-key.pem \
  -out /ssl/agent-suite.csr \
  -subj "/CN=agent-suite.local" \
  -addext "subjectAltName=DNS:agent-suite.local,IP:192.168.1.58"
```

Installez ensuite le certificat ou la chaîne retournée par la CA sous le nom
configuré dans `certfile`.

### Contrôler les fichiers et le listener

```sh
openssl x509 -in /ssl/agent-suite-cert.pem \
  -noout -subject -issuer -dates -fingerprint -sha256 -ext subjectAltName
openssl pkey -in /ssl/agent-suite-key.pem -check -noout
```

Pour comparer la clé publique du certificat et celle de la clé privée, les deux
commandes suivantes doivent produire le même condensat :

```sh
openssl x509 -in /ssl/agent-suite-cert.pem -pubkey -noout \
  | openssl pkey -pubin -outform DER | openssl dgst -sha256
openssl pkey -in /ssl/agent-suite-key.pem -pubout -outform DER \
  | openssl dgst -sha256
```

Contrôle indépendant de l’empreinte réellement servie :

```sh
openssl s_client -connect HOTE:PORT -servername NOM_DNS </dev/null 2>/dev/null \
  | openssl x509 -noout -fingerprint -sha256
```

Test du healthcheck HTTPS (l’option `-k` ne valide que la disponibilité et ne
doit pas remplacer la vérification de confiance dans un client réel) :

```sh
curl -k -i https://HOTE:PORT/health/ready
```

### Confiance des connexions sortantes

| Destination | HTTP | HTTPS sans empreinte | HTTPS avec empreinte |
|---|---|---|---|
| AEP → ACP | Autorisé, averti | CA, nom et dates vérifiés | SHA-256 exacte vérifiée avant le credential |
| ACP → connecteur MCP | Autorisé, averti | CA, nom et dates vérifiés | SHA-256 exacte vérifiée avant le secret |
| AEP autonome → MCP | Autorisé, averti | CA, nom et dates vérifiés | SHA-256 exacte vérifiée avant le secret |
| MCP Bridge → cible Web | Autorisé, averti | CA, nom et dates vérifiés | SHA-256 exacte vérifiée avant la requête |

L’empreinte doit contenir 64 chiffres hexadécimaux; les `:` et les différences
de casse sont normalisés. Elle est comparée au certificat présenté sur la
connexion TLS avant tout Bearer, credential, payload ou appel d’outil. Une
empreinte erronée provoque un refus fermé. La cible Web du Bridge conserve en
plus une désactivation explicite de la validation TLS comme solution de
compatibilité non sûre; l’interface et les logs la signalent clairement.

### Rotation

1. Remplacez le certificat externe ou utilisez **Régénérer le certificat**.
2. Redémarrez l’App serveur.
3. Relevez l’empreinte servie depuis un poste indépendant.
4. Remplacez l’empreinte chez chaque partenaire puis validez la connexion.

Un refus `certificate_sha256_mismatch` entre les étapes 2 et 4 est attendu et
prouve que l’ancien certificat n’est plus accepté silencieusement.

### Échecs, état du service et dépannage

Avant d’ouvrir un listener HTTPS, chaque App vérifie le fichier, la clé, leur
correspondance, la période de validité et `CA:FALSE`. En cas d’échec :

- le listener public HTTPS concerné ne démarre pas;
- l’administration Ingress reste disponible;
- la page d’ensemble indique **Service dégradé** ou **Service indisponible**;
- **Transport & TLS** indique **Listener non démarré** et la cause;
- un log anglais unique et exploitable est émis.

| Cause | Code ou erreur attendu |
|---|---|
| Fichier absent ou illisible | `FileNotFoundError` ou `PermissionError` |
| PEM invalide | erreur de chargement du certificat ou de la clé |
| Certificat et clé différents | `certificate_private_key_mismatch` |
| Certificat pas encore valide | `certificate_not_yet_valid` |
| Certificat expiré | `certificate_expired` |
| Certificat de CA utilisé comme serveur | `ca_certificate_not_allowed` |

Dans ACP, une erreur TLS n’arrête que les surfaces configurées en HTTPS :
l’administration Ingress et l’API événements configurée en HTTP restent
disponibles. Après correction, redémarrez toujours l’App.

### Validation officielle

Les trois Apps ont été validées sur HAOS réel le 24 août 2026 avec : HTTP,
HTTPS autogénéré, persistance et renouvellement, certificat externe valide,
fichiers absents, permissions, paire non correspondante, certificat expiré,
certificat de CA, refus d’empreinte erronée et reprise avec la bonne empreinte.
Les flux AEP→ACP, ACP→MCP Bridge et MCP Bridge→cible Web ont été vérifiés.

La CI complète cette acceptation avec
`scripts/agent_suite_tls_smoke.sh` et `scripts/external_tls_key_smoke.sh`.

---

## English

### Scope and defaults

TLS protects the Apps' public surfaces. Administration remains available only
through Home Assistant Ingress on internal port `8099`; HAOS owns its security,
and these Apps do not configure it.

| App | Public surface | Internal port | Default |
|---|---|---:|---|
| ACP | Event Intake API, `/api/v1/events` | `8100` | HTTP |
| ACP | MCP/worker endpoint, `/mcp` | `8098` | self-generated HTTPS |
| AEP | Standalone API | `8098` | self-generated HTTPS |
| MCP Bridge | MCP endpoint, `/mcp` | `8098` | self-generated HTTPS |

ACP's two surfaces are independent so event producers limited to HTTP remain
compatible. They share one certificate when both use HTTPS. Host ports are
selected in the Home Assistant App **Network** section.

For every public surface, the administrator selects:

- `http`: compatible but unencrypted; logs and **Transport & TLS** show an
  explicit warning;
- `https` with `self_generated`: the App creates and persists its certificate,
  and peers verify its SHA-256 fingerprint;
- `https` with `external`: the administrator supplies and renews the
  certificate and key and ensures clients trust its CA.

External non-TLS servers, including HA-MCP, remain supported through an
`http://` URL. This is an intentional, explicitly warned choice.

### Self-generated certificate

The certificate and key live under `/data/private/tls`, survive restarts, and
are included in the App data backup. The certificate is valid for five years.
Its SHA-256 fingerprint and expiry appear in **Transport & TLS** and in English
logs.

**Regenerate certificate** requires confirmation. The new certificate takes
effect after an App restart and normally changes the fingerprint. There is no
dual-pin grace period: update every peer with the new fingerprint after
verifying it through an independent channel.

### External certificate and `/ssl`

Put the certificate and key in the Home Assistant `/ssl` share. Enter **only
their share-relative filenames** in App options:

```yaml
certificate_source: external
certfile: agent-suite-cert.pem
keyfile: agent-suite-key.pem
```

`agent-suite-cert.pem` therefore resolves to `/ssl/agent-suite-cert.pem` inside
the container. Do not enter `/ssl/agent-suite-cert.pem`. A relative path into a
subdirectory of `/ssl` is accepted; absolute paths, `..` traversal outside
`/ssl`, and any external resolution are rejected. `/ssl` is mounted read-only.

Recommended permissions, validated on HAOS:

```sh
chmod 644 /ssl/agent-suite-cert.pem
chmod 600 /ssl/agent-suite-key.pem
```

At startup, the privileged bootstrap reads the key from `/ssl`, keeps it only
in memory, and permanently drops to UID/GID `1000`. It does not copy or stage
the key. Back up `/ssl` independently because it is outside App private data.

The certificate must be PEM, currently valid, use
`basicConstraints CA:FALSE`, match the private key, and be suitable for TLS
server authentication. For normal CA validation, its SAN must contain the DNS
name or IP address clients actually use. The PEM key must be unencrypted because
the Apps do not request a key password at startup. `certfile` may contain the
complete server chain (leaf first, followed by intermediates).

### Generate a self-signed server certificate with OpenSSL

Adapt the DNS name and IP address before running this example:

```sh
openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
  -keyout /ssl/agent-suite-key.pem \
  -out /ssl/agent-suite-cert.pem \
  -subj "/CN=agent-suite.local" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth" \
  -addext "subjectAltName=DNS:agent-suite.local,IP:192.168.1.58"
chmod 600 /ssl/agent-suite-key.pem
chmod 644 /ssl/agent-suite-cert.pem
```

Because it is self-signed, peers must pin its SHA-256 fingerprint unless they
explicitly add it to a trust store. For conventionally trusted TLS, create a
CSR with the same SAN and have an internal or public CA sign it:

```sh
openssl req -new -newkey rsa:2048 -sha256 -nodes \
  -keyout /ssl/agent-suite-key.pem \
  -out /ssl/agent-suite.csr \
  -subj "/CN=agent-suite.local" \
  -addext "subjectAltName=DNS:agent-suite.local,IP:192.168.1.58"
```

Install the CA-returned certificate or full chain under the configured
`certfile` name.

### Inspect files and the live listener

```sh
openssl x509 -in /ssl/agent-suite-cert.pem \
  -noout -subject -issuer -dates -fingerprint -sha256 -ext subjectAltName
openssl pkey -in /ssl/agent-suite-key.pem -check -noout
```

These commands must print the same public-key digest:

```sh
openssl x509 -in /ssl/agent-suite-cert.pem -pubkey -noout \
  | openssl pkey -pubin -outform DER | openssl dgst -sha256
openssl pkey -in /ssl/agent-suite-key.pem -pubout -outform DER \
  | openssl dgst -sha256
```

Independently inspect the certificate actually served:

```sh
openssl s_client -connect HOST:PORT -servername DNS_NAME </dev/null 2>/dev/null \
  | openssl x509 -noout -fingerprint -sha256
```

HTTPS readiness check (`-k` tests availability only and must not replace trust
verification in a real client):

```sh
curl -k -i https://HOST:PORT/health/ready
```

### Outbound trust

| Destination | HTTP | HTTPS without a pin | HTTPS with a pin |
|---|---|---|---|
| AEP → ACP | Allowed, warned | CA, hostname, and dates verified | Exact SHA-256 checked before credentials |
| ACP → MCP connector | Allowed, warned | CA, hostname, and dates verified | Exact SHA-256 checked before secrets |
| Standalone AEP → MCP | Allowed, warned | CA, hostname, and dates verified | Exact SHA-256 checked before secrets |
| MCP Bridge → Web target | Allowed, warned | CA, hostname, and dates verified | Exact SHA-256 checked before the request |

A fingerprint contains 64 hexadecimal digits; colons and letter case are
normalized. It is compared with the certificate on the established TLS socket
before any Bearer, credential, payload, or tool call is sent. A mismatch fails
closed. Bridge Web targets additionally retain an explicit insecure TLS
verification override for compatibility; the UI and logs clearly warn about
it.

### Rotation

1. Replace the external certificate or select **Regenerate certificate**.
2. Restart the server App.
3. Read the served fingerprint from an independent machine.
4. Replace the fingerprint on each peer and validate the connection.

A `certificate_sha256_mismatch` refusal between steps 2 and 4 is expected and
proves that the former certificate is not silently trusted.

### Failure containment and troubleshooting

Before opening an HTTPS listener, every App validates the file, private key,
key match, validity window, and `CA:FALSE`. On failure:

- the affected public HTTPS listener does not start;
- Ingress administration remains available;
- Overview reports **Service degraded** or **Service unavailable**;
- **Transport & TLS** reports **Listener not started** and the cause;
- one actionable English log entry is emitted.

| Cause | Expected code or error |
|---|---|
| Missing or unreadable file | `FileNotFoundError` or `PermissionError` |
| Invalid PEM | certificate or key loading error |
| Certificate/key mismatch | `certificate_private_key_mismatch` |
| Certificate not valid yet | `certificate_not_yet_valid` |
| Expired certificate | `certificate_expired` |
| CA certificate used as a server leaf | `ca_certificate_not_allowed` |

In ACP, a TLS error only stops surfaces configured for HTTPS: Ingress and an
HTTP Event Intake API remain available. Always restart the App after fixing the
configuration.

### Official validation

All three Apps were validated on real HAOS on 24 August 2026 with HTTP,
self-generated HTTPS, persistence and renewal, a valid external certificate,
missing files, permissions, a mismatched key pair, expired and CA certificates,
wrong-pin rejection, and recovery with the correct pin. AEP→ACP, ACP→MCP
Bridge, and MCP Bridge→Web target flows were verified.

CI complements this acceptance through `scripts/agent_suite_tls_smoke.sh` and
`scripts/external_tls_key_smoke.sh`.

For implementation rationale and threat boundaries, see
[TLS_TRANSPORT_DESIGN.md](TLS_TRANSPORT_DESIGN.md).
