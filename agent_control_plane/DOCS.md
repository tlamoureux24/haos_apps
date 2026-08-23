# Agent Control Plane

[Français](#français) | [English](#english)

Guide opérateur exhaustif : [français](README.fr.md) | [English](README.md). Il détaille chaque champ, les contrats JSON, les arguments fixes et les exemples Home Assistant.

---

## Français

Agent Control Plane (ACP) orchestre des tâches pour des agents compatibles MCP.
Il relie des événements, des planifications et des demandes manuelles à des
tâches qui n'exposent que les outils MCP explicitement autorisés par
l'administrateur.

Cette page fournit le démarrage guidé directement depuis Home Assistant. Le guide
français complet, avec l'explication détaillée de chaque paramètre, les limites,
les exemples d'événements, la corrélation, le dépannage et la sécurité, est dans
[README.fr.md](README.fr.md).

### Les objets à connaître

- **Connecteur** : connexion à un serveur MCP amont et inventaire de ses outils.
- **Tâche** : instructions transmises à l'agent + outils précisément autorisés.
- **Identité** : client authentifié avec un credential Bearer et des permissions.
- **Source d'événements** : identité qui peut publier des événements vers ACP.
- **Déclencheur** : associe une source et un `event_type` à une tâche.
- **Planification** : crée périodiquement une exécution d'une tâche.
- **Exécution** : travail persistant en attente ou en cours.
- **Rapport** : résultat structuré produit par l'agent.
- **Audit** : journal append-only des décisions et opérations.

### Installation et réseau

1. Installer **Agent Control Plane** depuis ce dépôt.
2. Démarrer l'App et ouvrir son Ingress.
3. Le port public `8100/tcp` n'est pas publié par défaut. Ne le publier que si un
   client MCP ou une source d'événements doit joindre ACP directement.
4. Si `8100` est publié tel quel :

```text
MCP :       https://IP_HOME_ASSISTANT:8098/mcp
Événements: http://IP_HOME_ASSISTANT:8100/api/v1/events
```

Ne pas exposer ce listener directement sur Internet ; utiliser un LAN ou VPN de
confiance.

Options principales de l'App :

| Option | Défaut | Rôle |
| --- | --- | --- |
| `log_level` | `info` | Niveau de logs (`debug`, `info`, `warning`, `error`) |
| `intake_rate_limit_per_minute` | `30` | Limite d'événements par minute et par identité source, plage 1 à 600 |

### Premier workflow MCP

1. **Connecteurs** → **Ajouter un connecteur**.
   - **Nom** : nom lisible.
   - **URL Streamable HTTP** : endpoint MCP complet, par exemple
     `http://serveur:8765/mcp`.
   - **Jeton Bearer** : facultatif, uniquement si le serveur amont l'exige.
2. ACP teste la connexion, découvre les outils et valide leurs schémas avant
   d'enregistrer le connecteur.
3. **Tâches** → **Nouvelle tâche**.
   - saisir un nom ;
   - écrire les instructions destinées à l'agent ;
   - choisir le nombre maximal de tentatives ;
   - ajouter uniquement les outils nécessaires.
4. Pour chaque outil :
   - **Standard** expose le schéma admis complet ;
   - **Restreint — arguments fixes** permet de rendre un argument modifiable par
     l'agent, fixe ordinaire, fixe sensible ou non exposé lorsqu'il est facultatif.
5. **Identités** → créer un **Client MCP** avec **Traiter les tâches** et, selon
   le besoin, **Lire les rapports**. Le credential n'est affiché qu'une seule
   fois.
6. Configurer le client MCP avec `/mcp` et ce credential en Bearer.

### Comprendre les arguments fixes

Les arguments fixes réduisent la surface que l'agent peut contrôler. ACP valide
l'appel réduit de l'agent, injecte ensuite les valeurs fixes, puis revalide
l'appel complet contre le schéma MCP amont.

- **Modifiable par l'agent** : visible dans le schéma agent.
- **Valeur fixe ordinaire** : cachée à l'agent et injectée par ACP.
- **Valeur fixe sensible** : cachée, protégée au repos et jamais réaffichée.
- **Non exposé** : propriété facultative retirée sans valeur injectée.

### Home Assistant → ACP : configuration pas à pas

Le flux est :

```text
Automatisation HA → rest_command → API événements ACP → Déclencheur → Tâche
```

#### 1. Créer l'identité de Home Assistant

Dans **Identités → Nouvelle identité** :

```text
Nom : Home Assistant Events
Type : Source d'événements
Permission : Créer des événements
```

Pour une source qui ne fait qu'envoyer des événements, `events.create` suffit.
Copier immédiatement le credential affiché.

#### 2. Stocker le credential dans `secrets.yaml`

```yaml
acp_event_authorization: "Bearer COLLEZ_ICI_LE_CREDENTIAL_ACP"
```

Le fichier `secrets.yaml` évite de placer le credential dans
`configuration.yaml`, mais il n'est pas chiffré : protéger l'accès à la
configuration et aux sauvegardes.

#### 3. Créer le `rest_command`

Dans `configuration.yaml` :

```yaml
rest_command:
  acp_event:
    url: "http://192.168.1.10:8100/api/v1/events"
    method: post
    content_type: "application/json"
    headers:
      Authorization: !secret acp_event_authorization
      Idempotency-Key: "{{ idempotency_key }}"
    payload: >-
      {{
        {
          "schema_version": 1,
          "event_type": event_type,
          "occurred_at": occurred_at,
          "subject": subject | default({}),
          "attributes": attributes | default({})
        } | to_json
      }}
```

Remplacer l'adresse IP et le port par ceux réellement utilisés. Si une section
`rest_command:` existe déjà, ajouter simplement `acp_event:` dessous. Redémarrer
Home Assistant après l'ajout initial afin de charger la configuration.

#### 4. Contrat événementiel attendu par ACP

L'API accepte exactement :

```json
{
  "schema_version": 1,
  "event_type": "service.alert",
  "occurred_at": "2026-08-19T16:30:00+00:00",
  "subject": {
    "service": "camera_duo2"
  },
  "attributes": {
    "status": "unreachable",
    "message": "Timeout"
  }
}
```

Concept essentiel :

```text
subject    = QUI / QUELLE ressource est concernée ?
attributes = QU'EST-CE QUI lui arrive ?
```

Le `subject` doit rester stable entre une alerte et son recovery. Les données
variables — état, message, timestamp d'observation, latence, compteur — vont dans
`attributes`.

`occurred_at` doit contenir un fuseau horaire. ACP refuse un timestamp de plus de
24 h dans le passé ou de plus de 5 min dans le futur.

`Idempotency-Key` est obligatoire, de 1 à 160 caractères. La même clé, pour la
même identité source, représente un retry du même événement et ne doit pas créer
un doublon.

#### 5. Créer le déclencheur ACP correspondant

Dans **Déclencheurs → Nouveau déclencheur** :

- **Nom** : purement lisible.
- **Source d'événements** : doit être l'identité qui envoie le Bearer.
- **Type d'événement** : doit être exactement le `event_type` du JSON.
- **Tâche** : tâche qui sera créée si le déclencheur aboutit.
- **Entrée transmise à l'agent** : choix expliqué ci-dessous.
- **Délai de grâce** : attente avant de créer le job.
- **Type de rétablissement** : obligatoire dès qu'une grâce est définie.
- **Corrélation** : Simple ou Agrégée par sujet.
- **Cooldown** : durée minimale entre deux déclenchements effectifs.

#### 6. Comprendre « Entrée transmise à l'agent »

**Événement complet** (`full_event`) : l'agent reçoit `schema_version`,
`event_type`, `occurred_at`, `subject` et `attributes`. À choisir lorsque
l'identité de la ressource et le contexte complet sont utiles.

**Sujet uniquement** (`subject`) : l'agent reçoit uniquement l'objet `subject`.
À choisir si connaître la ressource suffit à la tâche.

**Attributs uniquement** (`attributes`) : en corrélation Simple, l'agent reçoit
uniquement `attributes`. Le `subject` n'est pas ajouté automatiquement. À choisir
seulement si les attributs contiennent tout ce dont la tâche a besoin.

En corrélation **Agrégée par sujet**, ACP construit une enveloppe spéciale. Avec
**Attributs uniquement**, chaque entrée garde son `subject` à côté de ses
`attributes`, par exemple :

```json
{
  "schema_version": 1,
  "kind": "aggregated_event_incident",
  "event_type": "service.alert",
  "opened_at": "...",
  "due_at": "...",
  "subjects": [
    {
      "subject": {"service": "camera_duo2"},
      "attributes": {"status": "unreachable"}
    }
  ]
}
```

#### 7. Grâce, recovery et corrélation

**Sans grâce** : une alerte valide crée immédiatement un job si la tâche est
libre, le cooldown terminé et la file disponible.

**Grâce Simple** :

- première alerte → incident ouvert ;
- alertes répétées → dernière entrée actualisée sans repousser l'échéance ;
- recovery → incident entier annulé ;
- expiration → un job avec la dernière entrée.

**Grâce Agrégée par sujet** :

- le `subject` doit être non vide et stable ;
- plusieurs ressources peuvent rejoindre le même incident ;
- un recovery retire seulement le sujet exactement correspondant ;
- un recovery inconnu ne retire rien d'autre ;
- si tous les sujets récupèrent avant l'échéance, aucun job n'est créé ;
- à l'échéance, un seul job contient les sujets encore actifs.

La première alerte fixe l'échéance ; les alertes suivantes ne la prolongent
jamais.

**Cooldown** : empêche des jobs trop rapprochés après un vrai déclenchement. Il
est distinct de la grâce.

#### 8. Test manuel Home Assistant

Après avoir créé un déclencheur `service.alert`, appeler :

```yaml
action: rest_command.acp_event
data:
  event_type: "service.alert"
  occurred_at: "{{ utcnow().isoformat() }}"
  idempotency_key: "manual-acp-test-001"
  subject:
    service: "acp_manual_test"
  attributes:
    message: "Test envoyé depuis Home Assistant"
    status: "unreachable"
```

Vérifier ensuite **ACP → Événements**. Pour créer un deuxième événement logique,
utiliser une autre `idempotency_key`.

#### 9. Automatisation alerte + recovery

Exemple avec un `binary_sensor` :

```yaml
alias: "ACP - Supervision service exemple"
mode: queued
max: 10

triggers:
  - trigger: state
    entity_id: binary_sensor.example_service
    to: "off"
    id: alert

  - trigger: state
    entity_id: binary_sensor.example_service
    to: "on"
    id: recovered

actions:
  - action: rest_command.acp_event
    data:
      event_type: >-
        {{ 'service.alert' if trigger.id == 'alert' else 'service.recovered' }}
      occurred_at: "{{ trigger.to_state.last_changed.isoformat() }}"
      idempotency_key: "ha-{{ trigger.to_state.context.id }}-{{ trigger.id }}"
      subject:
        entity_id: "{{ trigger.entity_id }}"
        service: "example_service"
      attributes:
        state: "{{ trigger.to_state.state }}"
        previous_state: >-
          {{ trigger.from_state.state if trigger.from_state is not none else 'unknown' }}
        friendly_name: >-
          {{ state_attr(trigger.entity_id, 'friendly_name') or trigger.entity_id }}
```

Le point important est que l'alerte et le recovery réutilisent le même `subject`
stable. Les états changeants restent dans `attributes`.

Pour Gatus, une convention simple est `gatus.alert` / `gatus.recovered`, avec par
exemple `{"endpoint":"CAM DUO2"}` comme sujet stable. Les noms exacts des champs
reçus de l'événement Home Assistant `gatus_alert` doivent être inspectés sur
l'installation puis répartis entre `subject` et `attributes` selon leur stabilité.

### Planifications

Une planification cible une tâche prête et peut fonctionner :

- par **intervalle** ;
- **chaque jour** à `HH:MM` avec un fuseau IANA tel que `Europe/Paris` ;
- **chaque semaine**, avec jour + heure + fuseau.

Les occurrences manquées pendant un arrêt ne sont pas rejouées en rafale. Si la
tâche est déjà active, indisponible ou si la file est pleine, l'occurrence est
notée comme ignorée/échouée et l'échéance suivante est calculée normalement.

### Exécutions et rapports

États principaux :

- `queued` : en attente ;
- `leased` : en cours ;
- `completed` : terminée ;
- `failed` : échec non réessayable ;
- `dead_letter` : tentatives réessayables épuisées ;
- `cancelled` : annulée avant prise en charge.

Un lease vaut initialement 5 minutes et peut être prolongé par heartbeat jusqu'à
30 minutes maximum depuis sa prise en charge.
Les appels terminaux `jobs_complete_v1` et `jobs_fail_v1` utilisent une
`completion_key` opaque afin qu'une livraison puisse être répétée sans rejouer la
transition après une réponse réseau perdue.

Le rapport final contient `schema_version`, un `summary` non vide et un tableau
`findings`.

### Audit et rétention

La chaîne d'audit est vérifiée par HMAC au démarrage, périodiquement, sur demande
et après incohérence. L'export JSONL est disponible depuis l'interface.

La rétention des données opérationnelles terminées est de 90 jours par défaut.
Les jobs actifs, la configuration et l'audit ne sont pas supprimés par cette
rétention.

### Dépannage rapide Home Assistant

| HTTP / symptôme | Cause probable |
| --- | --- |
| `401` | Bearer absent, invalide ou révoqué |
| `403` | identité authentifiée sans `events.create` |
| `413` | corps supérieur à 32 Kio |
| `422` | payload, timestamp, clé d'idempotence, mapping ou dépendance invalide |
| `429` | limite d'ingestion dépassée |
| `503` | file pleine au moment de créer le job |
| événement sans job | grâce, recovery, cooldown, tâche déjà active ou doublon possible |

Pour le diagnostic complet, les limites précises, tous les résultats
d'événements, les restrictions d'outils, la sécurité, les sauvegardes et le cycle
de vie, consulter [README.fr.md](README.fr.md).

---

## English

Agent Control Plane (ACP) orchestrates tasks for MCP-compatible agents. It maps
events, schedules, and manual requests to tasks that expose only the MCP tools
explicitly authorized by the administrator.

This page provides an in-Home-Assistant guided setup. The complete English guide,
with every parameter, limit, event example, correlation behavior,
troubleshooting, and security detail, is in [README.md](README.md).

### Main objects

- **Connector**: connection to one upstream MCP server and its tool inventory.
- **Task**: agent instructions plus the exact allowed tools.
- **Identity**: authenticated caller with a Bearer credential and permissions.
- **Event source**: identity allowed to publish events to ACP.
- **Trigger**: maps one source and one `event_type` to a task.
- **Schedule**: periodically creates an execution of a task.
- **Execution**: persistent queued/running work item.
- **Report**: structured agent result.
- **Audit**: append-only governance journal.

### Installation and networking

1. Install **Agent Control Plane** from this repository.
2. Start the App and open Ingress.
3. Public `8100/tcp` is unpublished by default. Publish it only when an MCP client
   or event source needs direct access.
4. When mapped as host port `8100`:

```text
MCP:    https://HOME_ASSISTANT_IP:8098/mcp
Events: http://HOME_ASSISTANT_IP:8100/api/v1/events
```

Use only a trusted LAN or VPN; do not expose the listener directly to the
Internet.

Main App options:

| Option | Default | Role |
| --- | --- | --- |
| `log_level` | `info` | Runtime log level (`debug`, `info`, `warning`, `error`) |
| `intake_rate_limit_per_minute` | `30` | Event limit per minute per source identity, range 1 to 600 |

### First MCP workflow

1. **Connectors** → **Add connector**.
   - **Name**: human-readable name.
   - **Streamable HTTP URL**: full MCP endpoint, e.g. `http://server:8765/mcp`.
   - **Bearer token**: optional, only if the upstream server requires it.
2. ACP tests the connection, discovers tools, and validates schemas before
   storing the connector.
3. **Tasks** → **New task**.
   - name the task;
   - write agent instructions;
   - choose maximum attempts;
   - add only required tools.
4. Each tool may stay **Standard** or use **Restricted — fixed arguments**.
5. **Identities** → create an **MCP client** with **Process jobs** and, when
   needed, **Read reports**. The credential is shown once.
6. Configure the MCP client with `/mcp` and the credential as Bearer.

### Fixed arguments

Fixed arguments reduce the surface controlled by the agent. ACP validates the
agent's reduced call, injects fixed values, then validates the full upstream
call.

- **Agent editable**: stays visible to the agent.
- **Ordinary fixed**: hidden and injected by ACP.
- **Sensitive fixed**: hidden, protected at rest, never redisplayed.
- **Not exposed**: optional property removed and not injected.

### Home Assistant → ACP step by step

Flow:

```text
HA automation → rest_command → ACP event API → Trigger → Task
```

#### 1. Create the Home Assistant identity

Under **Identities → New identity**:

```text
Name: Home Assistant Events
Type: Event source
Permission: Create events
```

For a pure event publisher, `events.create` is enough. Copy the one-time
credential immediately.

#### 2. Store the credential in `secrets.yaml`

```yaml
acp_event_authorization: "Bearer PASTE_THE_ACP_CREDENTIAL_HERE"
```

`secrets.yaml` keeps the credential out of `configuration.yaml`, but it is not
encrypted. Protect Home Assistant configuration access and backups.

#### 3. Create the `rest_command`

In `configuration.yaml`:

```yaml
rest_command:
  acp_event:
    url: "http://192.168.1.10:8100/api/v1/events"
    method: post
    content_type: "application/json"
    headers:
      Authorization: !secret acp_event_authorization
      Idempotency-Key: "{{ idempotency_key }}"
    payload: >-
      {{
        {
          "schema_version": 1,
          "event_type": event_type,
          "occurred_at": occurred_at,
          "subject": subject | default({}),
          "attributes": attributes | default({})
        } | to_json
      }}
```

Replace IP/port with your actual mapping. If `rest_command:` already exists, add
`acp_event:` below it instead of creating a second top-level section. Restart
Home Assistant after the initial addition.

#### 4. Event contract

ACP accepts exactly:

```json
{
  "schema_version": 1,
  "event_type": "service.alert",
  "occurred_at": "2026-08-19T16:30:00+00:00",
  "subject": {"service": "camera_duo2"},
  "attributes": {"status": "unreachable", "message": "Timeout"}
}
```

Core mental model:

```text
subject    = WHO / WHICH stable resource is affected?
attributes = WHAT is happening to it?
```

Keep `subject` stable across alert and recovery. Put changing status, message,
observation timestamp, latency, and counters in `attributes`.

`occurred_at` must include a timezone. ACP rejects timestamps more than 24 hours
old or more than 5 minutes in the future.

`Idempotency-Key` is mandatory, 1 to 160 characters. Reusing it for the same
source identity means retrying the same logical event rather than creating a new
one.

#### 5. Create the matching ACP trigger

Under **Triggers → New trigger** configure:

- **Name**: human-readable label.
- **Event source**: must match the identity whose Bearer is used.
- **Event type**: exact incoming `event_type`.
- **Task**: task to execute.
- **Input sent to agent**: explained below.
- **Grace period**: delay before job creation.
- **Recovery event type**: required when grace is enabled.
- **Correlation**: Simple or Aggregated by subject.
- **Cooldown**: minimum delay between effective triggers.

#### 6. Understand “Input sent to agent”

**Full event** (`full_event`): agent receives `schema_version`, `event_type`,
`occurred_at`, `subject`, and `attributes`.

**Subject only** (`subject`): agent receives only `subject`.

**Attributes only** (`attributes`): in Simple mode the agent receives only
`attributes`; `subject` is not added automatically.

In **Aggregated by subject** mode ACP builds a deterministic envelope. With
**Attributes only**, every item still contains its `subject` beside its
`attributes`:

```json
{
  "schema_version": 1,
  "kind": "aggregated_event_incident",
  "event_type": "service.alert",
  "opened_at": "...",
  "due_at": "...",
  "subjects": [
    {
      "subject": {"service": "camera_duo2"},
      "attributes": {"status": "unreachable"}
    }
  ]
}
```

#### 7. Grace, recovery, and correlation

**No grace**: a valid alert immediately queues a job when the task is free,
cooldown has expired, and queue capacity exists.

**Simple grace**:

- first alert opens one incident;
- repeated alerts update the latest input without extending the deadline;
- recovery cancels the whole incident;
- expiry creates one job from the latest input.

**Aggregated by subject**:

- every alert requires a non-empty stable `subject`;
- several resources can join one incident;
- recovery removes only the exact matching subject;
- unknown recovery removes nothing else;
- if every subject recovers before expiry, no job is created;
- expiry creates one job containing the subjects still active.

The first alert fixes the due time; later alerts never extend it.

**Cooldown** prevents jobs from being created too close together after an actual
trigger. It is distinct from grace.

#### 8. Manual Home Assistant test

After creating a `service.alert` trigger, call:

```yaml
action: rest_command.acp_event
data:
  event_type: "service.alert"
  occurred_at: "{{ utcnow().isoformat() }}"
  idempotency_key: "manual-acp-test-001"
  subject:
    service: "acp_manual_test"
  attributes:
    message: "Test sent from Home Assistant"
    status: "unreachable"
```

Then check **ACP → Events**. Use another idempotency key to create another logical
event.

#### 9. Complete alert + recovery automation

```yaml
alias: "ACP - Example service monitoring"
mode: queued
max: 10

triggers:
  - trigger: state
    entity_id: binary_sensor.example_service
    to: "off"
    id: alert

  - trigger: state
    entity_id: binary_sensor.example_service
    to: "on"
    id: recovered

actions:
  - action: rest_command.acp_event
    data:
      event_type: >-
        {{ 'service.alert' if trigger.id == 'alert' else 'service.recovered' }}
      occurred_at: "{{ trigger.to_state.last_changed.isoformat() }}"
      idempotency_key: "ha-{{ trigger.to_state.context.id }}-{{ trigger.id }}"
      subject:
        entity_id: "{{ trigger.entity_id }}"
        service: "example_service"
      attributes:
        state: "{{ trigger.to_state.state }}"
        previous_state: >-
          {{ trigger.from_state.state if trigger.from_state is not none else 'unknown' }}
        friendly_name: >-
          {{ state_attr(trigger.entity_id, 'friendly_name') or trigger.entity_id }}
```

The alert and recovery deliberately reuse the exact stable `subject`; changing
states remain in `attributes`.

For Gatus, a clean convention is `gatus.alert` / `gatus.recovered` with a stable
subject such as `{"endpoint":"CAM DUO2"}`. Inspect the actual Home Assistant
`gatus_alert` event on your installation, then map stable fields to `subject` and
changing fields to `attributes`.

### Schedules

A schedule targets a ready task and can run by **interval**, **daily** at a local
`HH:MM` plus an IANA timezone such as `Europe/Paris`, or **weekly** with weekday,
time, and timezone.

Missed occurrences while ACP is stopped are not replayed in a burst. If the task
is already active, unavailable, or the queue is full, that occurrence is recorded
accordingly and the next occurrence is still calculated.

### Executions and reports

Main states:

- `queued`;
- `leased`;
- `completed`;
- `failed`;
- `dead_letter`;
- `cancelled`.

A lease initially lasts 5 minutes and may be extended by heartbeat up to 30
minutes from claim time.
The terminal `jobs_complete_v1` and `jobs_fail_v1` calls use an opaque
`completion_key`, allowing safe delivery retries after a lost network response.

Final reports contain `schema_version`, a non-empty `summary`, and a `findings`
array.

### Audit and retention

The HMAC audit chain is checked at startup, periodically, on demand, and after an
inconsistency. JSONL export is available from the UI.

Terminal operational data defaults to 90-day retention. Active jobs,
configuration, and the audit trail are not deleted by that retention.

### Quick Home Assistant troubleshooting

| HTTP / symptom | Likely cause |
| --- | --- |
| `401` | missing, invalid, or revoked Bearer |
| `403` | authenticated identity lacks `events.create` |
| `413` | body larger than 32 KiB |
| `422` | invalid payload, timestamp, idempotency key, mapping, or dependency |
| `429` | source intake limit exceeded |
| `503` | queue full when a job must be created |
| event but no job | grace, recovery, cooldown, active task, or duplicate may be normal |

For full troubleshooting, exact limits, every event outcome, tool restrictions,
security, backups, and lifecycle behavior, read [README.md](README.md).

---

Public release references: [MCP compatibility](MCP_COMPATIBILITY.md),
[threat model](THREAT_MODEL.md), [implementation plan](IMPLEMENTATION_PLAN.md), and
[changelog](CHANGELOG.md).
