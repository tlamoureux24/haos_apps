# Agent Control Plane

Agent Control Plane (ACP) est une App Home Assistant qui orchestre des travaux entre
des sources d'événements, des planifications, des agents authentifiés et un ou
plusieurs serveurs MCP externes. ACP ne contient pas de modèle d'IA : il gouverne
**quand** une tâche doit être créée, **quel agent** peut la prendre et **quels outils
MCP précis** cet agent peut utiliser pour cette tâche.

ACP applique un modèle deny-by-default. Découvrir un outil MCP ne l'autorise pas.
Un outil devient utilisable uniquement lorsqu'un administrateur le sélectionne
dans une tâche. Au moment de l'exécution, ACP revalide la tâche, sa révision, le
connecteur, l'outil, l'empreinte de son schéma, l'identité appelante, le lease actif
et les éventuelles restrictions d'arguments.

Documentation anglaise : [README.md](README.md).

Références techniques : [compatibilité MCP](MCP_COMPATIBILITY.md),
[modèle de menace](THREAT_MODEL.md), [plan d'implémentation](IMPLEMENTATION_PLAN.md)
et [changelog](CHANGELOG.md).

---

## 1. Comprendre ACP en quelques minutes

Avant de configurer l'App, il est utile de connaître les objets principaux.

| Objet ACP | Rôle | Exemple |
| --- | --- | --- |
| **Connecteur** | Connexion à un serveur MCP amont et inventaire de ses outils | Serveur MCP Home Assistant |
| **Tâche** | Instructions données à l'agent + liste exacte des outils autorisés | Diagnostiquer une caméra indisponible |
| **Identité** | Identifiant authentifié avec des permissions précises | Codex, Home Assistant Events |
| **Source d'événements** | Identité autorisée à envoyer des événements à ACP | Automatisations Home Assistant |
| **Déclencheur** | Associe un type d'événement d'une source à une tâche | `gatus.alert` → diagnostic réseau |
| **Planification** | Crée périodiquement une exécution d'une tâche | Diagnostic quotidien à 09:00 |
| **Exécution** | Travail concret mis en file pour un agent | Job créé après une alerte |
| **Rapport** | Résultat structuré renvoyé par l'agent | Résumé + constats |
| **Audit** | Journal append-only des décisions et opérations | Création, refus, appel d'outil, rapport |

Le flux événementiel typique est :

```text
Home Assistant / autre source
        │
        │ POST /api/v1/events + Bearer
        ▼
  Source d'événements ACP
        │
        ▼
     Déclencheur
        │
        ├── sans grâce ───────────────► Exécution
        │
        └── avec grâce ► Incident ───► Recovery : annulation
                              │
                              └──────► expiration : Exécution
                                                │
                                                ▼
                                              Agent
                                                │
                                     outils MCP autorisés
                                                │
                                                ▼
                                              Rapport
```

Le flux manuel ou planifié commence directement par la tâche :

```text
Exécuter maintenant / Planification → Exécution → Agent → outils MCP → Rapport
```

---

## 2. Installation, réseau et options de l'App

1. Ajouter ce dépôt à la boutique des Apps Home Assistant.
2. Installer **Agent Control Plane**.
3. Démarrer l'App.
4. Ouvrir l'interface Ingress.

L'administration est volontairement accessible uniquement via l'Ingress
authentifié de Home Assistant.

### Ports publics 8098 et 8100

La réception d'événements utilise `8098` ; MCP et l'API REST worker utilisent
`8100`. Ce découpage préserve les producteurs limités à HTTP sans affaiblir MCP.

Dans la configuration réseau, associez `8098/tcp` pour les événements et
`8100/tcp` pour MCP aux ports hôte souhaités, puis utilisez ces ports dans les
URL clientes.

Exemples :

```text
MCP :       https://IP_HOME_ASSISTANT:8100/mcp
Événements: http://IP_HOME_ASSISTANT:8098/api/v1/events
```

Ne publiez pas ce listener directement sur Internet. Utilisez un LAN ou un VPN de
confiance.

### Options de l'App

| Option | Valeurs | Défaut | Explication |
| --- | --- | --- | --- |
| `log_level` | `debug`, `info`, `warning`, `error` | `info` | Niveau des logs runtime de l'App |
| `intake_rate_limit_per_minute` | 1 à 600 | 30 | Nombre maximal d'événements acceptés par minute et par identité source |
| `events_transport` | `http`, `https` | `http` | Transport des événements |
| `mcp_transport` | `http`, `https` | `https` | Transport MCP/worker |
| `certificate_source` | `self_generated`, `external` | `self_generated` | Source du certificat HTTPS partagé |

L’administration affiche l’empreinte SHA-256. Pour un certificat autogénéré,
les clients épinglent cette valeur après vérification indépendante. Toute
surface HTTP est non chiffrée et produit un avertissement anglais dans les logs.

La limite d'ingestion protège l'API événementielle. Une source qui dépasse la
limite reçoit HTTP `429` avec `Retry-After: 60`.

---

## 3. Vue d'ensemble

La page **Vue d'ensemble** est le cockpit opérationnel. Elle résume :

- connecteurs prêts, indisponibles, désactivés ou archivés ;
- tâches prêtes, indisponibles, désactivées ou archivées ;
- identités actives ;
- déclencheurs et planifications actifs ;
- événements et rapports récents ;
- exécutions en attente ou en cours ;
- incidents de grâce ;
- dead letters et échecs récents ;
- état de vérification de la chaîne d'audit.

Les vues opérationnelles **Vue d'ensemble**, **Événements**, **Rapports** et
**Audit** se rafraîchissent automatiquement toutes les 10 secondes.
**Exécutions** se rafraîchit toutes les 5 secondes. Le rafraîchissement est
suspendu lorsque l'onglet est masqué, lorsqu'un panneau d'administration est
ouvert ou lorsqu'un détail est déplié afin de ne pas perturber la lecture.

---

## 4. Connecteurs MCP

Un connecteur représente **un serveur MCP amont** dont ACP peut découvrir les
outils.

### Paramètres d'un nouveau connecteur

#### Nom

Nom lisible affiché dans ACP. Il n'est pas envoyé au serveur MCP.

Exemple :

```text
Home Assistant MCP
```

#### URL Streamable HTTP

URL complète du endpoint MCP amont, généralement terminée par `/mcp`.

Exemple :

```text
http://192.168.1.50:8765/mcp
```

Contraintes :

- schéma `http` ou `https` ;
- hôte obligatoire ;
- port valide de 1 à 65535 si présent ;
- maximum 2048 caractères ;
- aucun nom d'utilisateur ou mot de passe intégré dans l'URL ;
- aucun fragment `#...` ;
- les redirections HTTP ne sont pas suivies.

#### Jeton Bearer facultatif

À renseigner uniquement si le serveur MCP amont exige une authentification
Bearer. ACP ajoute alors :

```text
Authorization: Bearer <jeton>
```

Le secret est protégé au repos dans ACP. Il n'est jamais transmis aux agents et
n'est jamais réaffiché dans l'interface.

### Tester et ajouter

ACP initialise une session Streamable HTTP, appelle `tools/list`, valide les
schémas publiés et enregistre l'inventaire seulement si la connexion est
acceptable.

La découverte est bornée à 200 outils par connecteur. Chaque schéma d'entrée est
limité à 16 Kio. Le profil JSON Schema accepté est décrit dans
[MCP_COMPATIBILITY.md](MCP_COMPATIBILITY.md).

### États d'un connecteur

| État | Signification |
| --- | --- |
| `ready` | Connexion et inventaire valides |
| `disabled` | Connecteur volontairement désactivé |
| `unreachable` | Serveur ou transport inaccessible |
| `invalid` | Serveur joignable mais schéma MCP refusé |

Une tâche dépendante devient indisponible si son connecteur n'est plus prêt, si
un outil disparaît ou si l'empreinte du schéma d'un outil change.

### Vérifier

L'action **Vérifier** redécouvre l'inventaire. Une modification de schéma est
visible et ACP refuse de continuer à utiliser silencieusement un contrat qui a
changé.

### Modifier l'endpoint

Le nom peut être modifié sans remplacer le secret. Laisser la nouvelle URL vide
conserve l'endpoint protégé actuel. Remplacer l'URL relance la découverte.

Une modification de connexion est refusée tant qu'une exécution dépendante est
en attente ou louée.

### Rotation du secret

**Rotation du secret** remplace explicitement le Bearer stocké. Le secret actuel
n'est jamais prérempli. La nouvelle valeur est testée avant d'être adoptée.

Si le test échoue, l'ancien secret reste stocké. Si le test réussit, l'ancien
secret n'est plus conservé ni utilisé par ACP ; sa révocation côté serveur amont
reste à effectuer sur ce serveur.

### Désactiver, archiver, supprimer

- **Désactiver** : état temporaire ; le connecteur reste configuré.
- **Archiver** : le retire des vues opérationnelles normales tout en conservant
  l'historique. Une restauration le remet en état désactivé.
- **Supprimer** : suppression définitive autorisée seulement si aucune dépendance
  persistante ne l'utilise.

---

## 5. Tâches

Une tâche est le contrat de travail présenté à l'agent. Elle contient des
instructions et une liste explicite d'outils MCP autorisés.

### Nom

Nom humain de la tâche, par exemple :

```text
Diagnostic caméra indisponible
```

L'interface génère automatiquement un nom technique compatible à partir de ce
nom. Il est utilisé en interne et dans les exécutions.

### Instructions transmises à l'agent

C'est l'objectif de la tâche. Il doit décrire le résultat attendu, les limites et
le comportement souhaité.

Exemple :

```text
Analyse l'état du service concerné. Utilise uniquement les outils disponibles
pour cette tâche. Identifie la cause la plus probable, n'effectue aucune action
destructrice et rends un rapport concis avec les constats vérifiables.
```

Maximum : 4000 caractères.

### Tentatives maximales

Nombre maximal de tentatives d'exécution lorsque l'agent signale un échec
réessayable ou qu'un lease expire. La valeur technique acceptée est de 1 à 10.

Lorsque toutes les tentatives réessayables sont consommées, l'exécution passe en
**dead letter / À traiter**.

### Outils autorisés

Une tâche doit contenir au moins un outil provenant d'un connecteur prêt.
Sélectionner un outil est **l'acte d'autorisation** : un outil découvert mais non
sélectionné n'est pas disponible à l'agent.

Les outils sont publiés à l'agent sous des noms virtuels uniques liés à la
révision de tâche. Deux connecteurs peuvent donc exposer un outil amont portant
le même nom sans collision.

### Mode Standard

**Standard — schéma d'origine** expose à l'agent tout le schéma d'entrée admis de
l'outil. L'agent peut fournir tous les arguments autorisés par ce schéma.

Utilisez ce mode lorsque la totalité des paramètres de l'outil doit réellement
rester à la disposition de l'agent.

### Restreindre cet outil / arguments fixes

Le mode **Restreint — arguments fixes** réduit la surface visible par l'agent.
Pour chaque propriété de premier niveau du schéma, l'administrateur choisit :

| Exposition | Effet |
| --- | --- |
| **Modifiable par l'agent** | La propriété reste visible et l'agent fournit sa valeur |
| **Valeur fixe ordinaire** | La propriété disparaît du schéma agent ; ACP injecte la valeur configurée |
| **Valeur fixe sensible** | Même comportement, mais la valeur est protégée au repos et jamais réaffichée |
| **Non exposé** | Propriété facultative retirée de l'interface agent et non injectée |

Les propriétés obligatoires du schéma amont ne peuvent pas simplement être
omises : elles doivent rester modifiables ou recevoir une valeur fixe.

#### Valeur d'exemple

Le formulaire demande un **appel exemple valide**. ACP valide d'abord cet exemple
contre le schéma amont. Les valeurs fixes sont ensuite enregistrées dans le
contrat de la tâche.

À l'exécution :

1. ACP valide les arguments fournis par l'agent contre le schéma réduit ;
2. ACP refuse toute tentative de fournir un argument caché ;
3. ACP injecte les valeurs fixes ordinaires et sensibles ;
4. ACP valide l'appel complet contre le schéma amont ;
5. seulement ensuite, l'appel MCP est envoyé au connecteur.

Cette fonction est particulièrement utile pour figer un `entity_id`, un hôte,
un espace de travail, une portée ou un paramètre sensible que l'agent ne doit pas
pouvoir changer.

### Exécuter maintenant

Crée une exécution avec une entrée vide `{}`. ACP n'autorise qu'une exécution
en attente ou en cours à la fois pour une même tâche.

### Mettre en pause, archiver, supprimer

- désactiver une tâche empêche de nouvelles exécutions et supprime ses incidents
  de grâce en attente ;
- archiver une tâche désactive également ses planifications et déclencheurs ;
- une tâche avec une exécution en attente ou louée ne peut pas être archivée ;
- une tâche déjà référencée par des exécutions, planifications ou déclencheurs ne
  peut pas être supprimée tant que ces dépendances existent.

---

## 6. Identités et permissions

Une identité représente un appelant authentifié. Chaque identité possède son
propre credential Bearer et sa propre liste de permissions.

### Nom

Nom humain permettant de reconnaître l'appelant :

```text
Codex HAOS
Home Assistant Events
Supervision externe
```

### Type

| Type | Usage recommandé |
| --- | --- |
| **Client MCP** (`client`) | Agent/worker qui réclame et exécute des travaux |
| **Source d'événements** (`event_source`) | Système autorisé à publier des événements ; requis par les déclencheurs |
| **Planificateur** (`scheduler`) | Classe d'identité disponible pour un client externe de type planificateur ; les planifications internes de l'UI n'en ont pas besoin |

Un déclencheur événementiel ACP exige explicitement une identité active de type
**Source d'événements**.

### Permissions du plan de contrôle

| Permission UI | Action technique | Donne le droit de... |
| --- | --- | --- |
| Lire ses permissions | `permissions.effective.read` | Lire les droits effectifs de l'identité |
| Créer des événements | `events.create` | POSTer vers `/api/v1/events` |
| Lire les événements | `events.read` | Lire la collection d'événements publique |
| Lire les tâches/exécutions | `jobs.read` | Lire la collection des jobs |
| Traiter les tâches | `jobs.claim` + bundle worker | Réclamer, maintenir, terminer ou échouer un job |
| Lire les rapports | `reports.read` | Lire les rapports persistés |

Lorsque **Traiter les tâches** est coché, l'interface accorde également
`jobs.heartbeat`, `jobs.complete` et `jobs.fail`, nécessaires au cycle de vie du
worker.

Une source Home Assistant qui ne fait qu'envoyer des événements n'a normalement
besoin que de :

```text
events.create
```

### Credential affiché une seule fois

Après création, ACP affiche le credential une seule fois. Copiez-le immédiatement.
Il ne peut pas être récupéré ensuite. S'il est perdu, révoquez l'identité et
créez-en une nouvelle.

Ne placez jamais ce credential dans un dépôt Git, une capture d'écran ou un log.

### Révoquer

Révoquer une identité invalide immédiatement tous ses credentials actifs. Pour
une source d'événements, les incidents de grâce liés à cette source sont également
supprimés.

---

## 7. Événements : contrat public de l'API

Endpoint :

```text
POST http://IP_HOME_ASSISTANT:8098/api/v1/events
```

Headers obligatoires :

```text
Authorization: Bearer <credential de la source>
Content-Type: application/json
Idempotency-Key: <clé unique de l'événement logique>
```

Le credential doit appartenir à une identité possédant `events.create`.

### Corps JSON

ACP accepte un contrat strict de version 1 :

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

Aucun champ de premier niveau supplémentaire n'est accepté.

### `schema_version`

Doit être exactement :

```json
1
```

### `event_type`

Identifie la nature de l'événement et doit correspondre exactement au champ
**Type d'événement** du déclencheur ACP.

Contraintes :

- 1 à 120 caractères ;
- commence par une lettre minuscule ;
- caractères suivants : lettres minuscules, chiffres, `_`, `.`, `-`.

Exemples :

```text
gatus.alert
gatus.recovered
camera.offline
backup.failed
ups.on_battery
```

### `occurred_at`

Date/heure à laquelle l'événement s'est réellement produit. Un fuseau horaire est
obligatoire (`Z`, `+00:00`, `+02:00`, etc.). ACP normalise ensuite la valeur en
UTC.

ACP refuse un événement dont `occurred_at` est :

- plus de 24 heures dans le passé ;
- plus de 5 minutes dans le futur.

### `subject` : **qui est concerné ?**

`subject` doit contenir uniquement l'identité **stable** de la ressource ou du
sujet concerné.

Bon exemple :

```json
{
  "endpoint": "CAM DUO2",
  "site": "maison"
}
```

Mauvais exemple :

```json
{
  "endpoint": "CAM DUO2",
  "status": "down",
  "checked_at": "2026-08-19T18:21:00+02:00",
  "latency_ms": 3000
}
```

`status`, `checked_at` et `latency_ms` changent d'une observation à l'autre : ils
appartiennent à `attributes`.

Cette séparation est essentielle en corrélation **Agrégée par sujet**, car ACP
utilise le contenu canonique du `subject` pour reconnaître qu'une alerte et un
rétablissement concernent exactement la même ressource.

L'ordre des clés JSON n'a pas d'importance, mais les noms, types et valeurs oui.
`{"id":"1"}` et `{"id":1}` sont donc deux sujets différents.

### `attributes` : **qu'est-ce qui se passe ?**

`attributes` contient les données variables utiles à l'analyse :

```json
{
  "status": "unreachable",
  "message": "Connection timed out",
  "latency_ms": 3000,
  "attempt": 2
}
```

C'est ici que l'on place les observations, messages, métriques, états ou détails
que l'agent peut utiliser pour son diagnostic.

### Limites du payload événementiel

- corps HTTP : 32 Kio maximum ;
- `subject` : 32 champs maximum ;
- `attributes` : 32 champs maximum ;
- nom de clé dans `subject` ou `attributes` : 80 caractères maximum ;
- en corrélation agrégée, le `subject` canonique est limité à 4096 octets ;
- un incident agrégé contient au maximum 100 sujets ;
- l'entrée agrégée finale est limitée à 128 Kio.

### `Idempotency-Key`

La clé d'idempotence est obligatoire et doit contenir 1 à 160 caractères.

Son rôle est d'éviter qu'un retry réseau crée deux événements logiques. Pour une
même identité source, renvoyer la même clé retourne l'événement déjà enregistré
au lieu d'en créer un nouveau.

Choisissez donc une clé **stable pour un même événement**, mais différente pour
l'alerte suivante et pour son recovery.

Bon exemple :

```text
ha-01JABCDEF123-alert
ha-01JXYZ987654-recovered
```

Évitez une constante comme `home-assistant-event`, qui ferait considérer toutes
les requêtes futures comme des doublons.

### Réponse HTTP

Un nouvel événement valide retourne HTTP `202` :

```json
{
  "event_id": "...",
  "job_id": null,
  "duplicate": false,
  "status": "grace_started"
}
```

Un retry avec la même clé peut retourner HTTP `200` avec `duplicate: true`.

`job_id` peut être `null` même lorsque l'événement est parfaitement valide : par
exemple pendant une période de grâce, un cooldown, un recovery ou lorsqu'une
exécution de la même tâche est déjà active.

---

## 8. Déclencheurs : explication de chaque paramètre

Un déclencheur relie **une source + un type d'événement** à **une tâche**.
La source ne choisit jamais directement la tâche dans sa requête : cette décision
reste dans la configuration administrative d'ACP.

### Nom

Nom lisible du déclencheur.

Exemple :

```text
Gatus - panne équipement
```

### Source d'événements

Identité de type `event_source` qui a le droit d'envoyer cet événement.

Un même `event_type` envoyé avec le credential d'une autre identité ne correspond
pas à ce déclencheur.

### Type d'événement

Doit correspondre exactement au `event_type` reçu dans le JSON.

Exemple :

```text
gatus.alert
```

Pour une même source, ACP interdit les collisions entre types d'alerte et de
recovery de plusieurs déclencheurs afin qu'un événement ne soit pas ambigu.

### Tâche

Tâche à exécuter lorsque le déclencheur aboutit. Elle doit être prête au moment
de la configuration. Si elle devient indisponible ensuite, ACP échoue en mode
fermé et ne donne pas à l'agent un contrat partiellement valide.

### Entrée transmise à l'agent

Ce paramètre décide quelle partie de l'événement devient l'**entrée du job**.
Il ne change pas l'événement conservé dans la vue **Événements** ; il change ce
que l'agent reçoit pour travailler.

#### Événement complet (`full_event`)

L'agent reçoit :

```json
{
  "schema_version": 1,
  "event_type": "service.alert",
  "occurred_at": "...",
  "subject": {"service": "camera_duo2"},
  "attributes": {"status": "unreachable"}
}
```

Choisissez ce mode lorsque l'agent a besoin du type, de l'heure, de l'identité du
sujet **et** des observations.

#### Sujet uniquement (`subject`)

Sans agrégation, l'agent reçoit seulement :

```json
{
  "service": "camera_duo2"
}
```

Choisissez ce mode si l'objectif de la tâche et les outils suffisent à travailler
à partir de l'identité de la ressource.

#### Attributs uniquement (`attributes`)

Sans agrégation, l'agent reçoit seulement :

```json
{
  "status": "unreachable",
  "message": "Timeout"
}
```

Choisissez ce mode lorsque le sujet sert principalement à ACP pour la corrélation
et que les données utiles à la tâche sont dans `attributes`.

**Attention : en mode Simple, `attributes` n'inclut pas automatiquement le
`subject`.** Si l'agent doit savoir précisément quelle ressource est concernée,
utilisez `full_event` ou mettez dans `attributes` l'identifiant dont la tâche a
réellement besoin.

#### Cas particulier : Agrégée par sujet

En corrélation agrégée, ACP construit une enveloppe déterministe. Même avec
**Attributs uniquement**, chaque élément conserve son `subject` afin que l'agent
puisse rattacher les observations à la bonne ressource.

Exemple avec `input_mode = attributes` :

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
      "attributes": {"status": "unreachable", "message": "Timeout"}
    },
    {
      "subject": {"service": "camera_garage"},
      "attributes": {"status": "unreachable", "message": "No route"}
    }
  ]
}
```

Avec `full_event`, chaque élément contient `subject` + `event` complet.
Avec `subject`, chaque élément contient uniquement son `subject` dans l'enveloppe
agrégée.

C'est une différence importante entre **Simple** et **Agrégée par sujet**.

### Délai de grâce

Le délai de grâce évite de solliciter l'agent pour une panne qui se résout
rapidement.

Avec `5 minutes`, le premier événement d'alerte ouvre un incident dont l'échéance
est fixée à `maintenant + 5 minutes`.

Une alerte répétée **ne repousse pas l'échéance**. Elle actualise les données du
sujet concerné mais la première échéance reste immuable.

Avec une grâce supérieure à zéro, ACP exige un type d'événement de
rétablissement.

### Type d'événement de rétablissement

Exemple :

```text
gatus.recovered
```

Il doit être différent du type d'alerte.

Le recovery ne crée pas une nouvelle tâche. Il sert à résoudre tout ou partie de
l'incident de grâce.

Sans incident actif, le recovery est simplement enregistré et audité.

### Corrélation Simple

Le déclencheur possède un seul incident logique.

- première alerte : ouverture de l'incident ;
- alertes suivantes : mise à jour de la dernière entrée ;
- recovery : annulation de tout l'incident ;
- expiration : création d'une seule exécution avec la dernière entrée disponible.

Le `subject` n'a pas besoin d'être non vide pour la corrélation Simple.

### Corrélation Agrégée par sujet

Utilisez ce mode lorsqu'une même famille d'alertes peut concerner plusieurs
ressources pendant la même fenêtre de grâce.

Chaque alerte doit avoir un `subject` non vide et stable.

Exemple :

```text
18:00 CAM DUO2 en panne       → incident ouvert, 1 sujet
18:01 CAM GARAGE en panne     → même incident, 2 sujets
18:02 CAM DUO2 rétablie       → retrait de CAM DUO2, 1 sujet
18:05 échéance                → un seul job pour CAM GARAGE
```

Un recovery dont le `subject` n'existe pas dans l'incident est traité comme un
no-op audité : ACP ne supprime aucun autre sujet par approximation.

Lorsque le dernier sujet est rétabli avant l'échéance, l'incident disparaît et
aucun job n'est créé.

### Cooldown

Le cooldown limite la fréquence à laquelle un même déclencheur peut réellement
créer des jobs.

Il commence après un déclenchement effectif, c'est-à-dire lorsque le job a été
mis en file (immédiatement ou après la grâce). Une alerte reçue pendant le
cooldown est conservée et auditée mais ne crée pas un nouveau job.

Le cooldown est distinct de la grâce :

- **grâce** = attendre avant de décider si l'incident mérite une exécution ;
- **cooldown** = empêcher des exécutions trop rapprochées après un déclenchement.

### Une seule exécution active par tâche

Si la tâche cible possède déjà un job `queued` ou `leased`, ACP n'en crée pas un
second. L'événement est conservé avec le résultat `task_execution_active`.

### Promotion d'un incident après la grâce

À l'échéance, ACP vérifie à nouveau :

- déclencheur activé ;
- tâche activée et prête ;
- connecteurs et empreintes de schéma valides ;
- absence d'une autre exécution active de la tâche ;
- cooldown ;
- capacité de la file.

Si une condition temporaire bloque la promotion, ACP réessaie avec un backoff
borné. Après 10 tentatives, l'incident devient **bloqué** et reste visible dans
**Déclencheurs**. Le bouton **Relancer l'incident** remet les tentatives à zéro.

---

## 9. Section spéciale Home Assistant : envoyer des événements à ACP

Cette section est volontairement détaillée pour qu'une personne qui ne développe
pas puisse configurer le flux de bout en bout.

### Ce que nous allons construire

```text
Automatisation Home Assistant
        │
        ▼
rest_command.acp_event
        │
        │ Authorization: Bearer ...
        │ Idempotency-Key: ...
        ▼
http://IP_HA:8098/api/v1/events
        │
        ▼
Source d'événements ACP
        │
        ▼
Déclencheur ACP
        │
        ▼
Tâche / grâce / recovery / agent
```

### Prérequis

Avant de commencer :

1. ACP est installé et démarré ;
2. le port public de l'App est publié sur le LAN, par exemple `8098` ;
3. au moins un connecteur MCP est prêt ;
4. au moins une tâche ACP est prête ;
5. vous pouvez modifier `configuration.yaml` et `secrets.yaml` de Home Assistant.

### Étape 1 — Créer l'identité de Home Assistant dans ACP

Dans **ACP → Identités → Nouvelle identité** :

```text
Nom : Home Assistant Events
Type : Source d'événements
Permission : Créer des événements
```

Pour ce rôle, ne cochez pas les permissions de worker si elles ne sont pas
nécessaires.

Cliquez sur **Créer l'identité** puis copiez immédiatement le credential affiché.
Il ne sera plus visible après fermeture du panneau.

### Étape 2 — Stocker le Bearer dans `secrets.yaml`

Dans le fichier `secrets.yaml` de Home Assistant, ajoutez :

```yaml
acp_event_authorization: "Bearer COLLEZ_ICI_LE_CREDENTIAL_ACP"
```

Il est volontairement pratique de stocker la chaîne complète `Bearer ...` afin
que `configuration.yaml` ne contienne aucune partie du credential.

`secrets.yaml` évite de disperser le secret dans les fichiers de configuration,
mais **ce fichier n'est pas chiffré** : protégez l'accès à votre configuration et
à vos sauvegardes.

### Étape 3 — Créer le `rest_command`

Dans `configuration.yaml`, ajoutez :

```yaml
rest_command:
  acp_event:
    url: "http://192.168.1.10:8098/api/v1/events"
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

Remplacez `192.168.1.10` par l'adresse IP de votre Home Assistant et `8098` par
le port hôte réellement configuré pour ACP.

Pourquoi utiliser `to_json` ? Parce qu'il sérialise correctement les chaînes,
guillemets, nombres, booléens, dictionnaires et caractères spéciaux. Il est bien
plus sûr que de construire du JSON à la main avec des concaténations de chaînes.

Après ajout d'un `rest_command` dans `configuration.yaml`, redémarrez Home
Assistant pour charger cette configuration.

> Si vous avez déjà une section `rest_command:`, n'en créez pas une seconde :
> ajoutez simplement `acp_event:` sous la section existante avec la bonne
> indentation YAML.

### Étape 4 — Créer le déclencheur correspondant dans ACP

Avant le premier test, créez dans **ACP → Déclencheurs → Nouveau déclencheur** un
mapping qui accepte le type que vous allez envoyer.

Exemple sans grâce pour un premier test :

```text
Nom : Test Home Assistant
Source d'événements : Home Assistant Events
Type d'événement : service.alert
Tâche : votre tâche de test
Entrée transmise à l'agent : Événement complet
Délai de grâce : Aucun
Cooldown : Aucun
```

Pour le tout premier test, **Événement complet** est le choix le plus facile à
comprendre : le job affichera exactement les données métier envoyées par Home
Assistant.

### Étape 5 — Tester manuellement depuis Home Assistant

Appelez l'action `rest_command.acp_event` depuis les outils de développement de
Home Assistant avec :

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

Dans ACP, vérifiez ensuite **Événements**. Vous devez voir `service.alert` avec la
source **Home Assistant Events**.

Si le déclencheur n'a ni grâce ni cooldown et que la tâche est disponible, une
exécution doit également apparaître dans **Exécutions**.

Pour refaire un test en créant un nouvel événement, changez la clé :

```text
manual-acp-test-002
```

Si vous réutilisez `manual-acp-test-001`, ACP doit répondre comme un doublon et
ne pas recréer l'événement.

### Étape 6 — Automatisation Home Assistant complète avec alerte + recovery

L'exemple suivant surveille un `binary_sensor`. Adaptez l'entité et éventuellement
la polarité `on/off` à votre équipement.

```yaml
alias: "ACP - Supervision service exemple"
description: "Envoie une alerte et son recovery à Agent Control Plane"
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

Ce qui est important dans cet exemple :

- l'alerte utilise `service.alert` ;
- le recovery utilise `service.recovered` ;
- **le `subject` est identique et stable dans les deux cas** ;
- l'état courant et l'état précédent sont dans `attributes`, car ils changent ;
- la clé d'idempotence utilise le contexte du changement d'état et l'identifiant
  `alert`/`recovered`, donc alerte et recovery ne partagent pas la même clé ;
- `occurred_at` vient du changement d'état réel et contient un fuseau horaire.

### Étape 7 — Configurer la grâce et le recovery dans ACP

Pour transformer l'exemple précédent en anti-faux-positif :

```text
Nom : Supervision service exemple
Source : Home Assistant Events
Type d'événement : service.alert
Tâche : Diagnostic service
Entrée transmise : voir choix ci-dessous
Délai de grâce : 5 minutes
Type de rétablissement : service.recovered
Corrélation : Simple ou Agrégée par sujet
Cooldown : selon le besoin
```

#### Quel mode d'entrée choisir ici ?

- **Événement complet** : choix le plus sûr si l'agent doit connaître l'entité,
  l'heure et tous les détails.
- **Sujet uniquement** : si la tâche doit seulement savoir quelle ressource
  analyser.
- **Attributs uniquement + Simple** : seulement si les attributs contiennent
  réellement toutes les informations nécessaires à l'agent.
- **Attributs uniquement + Agrégée par sujet** : très pratique pour un incident
  multi-équipements ; ACP remet automatiquement chaque `subject` à côté de ses
  `attributes` dans l'enveloppe agrégée.

### Exemple de logique Gatus

Pour une supervision Gatus, une convention saine est :

```text
Alerte ACP   : gatus.alert
Recovery ACP : gatus.recovered
```

Le `subject` doit identifier l'endpoint de façon stable, par exemple :

```json
{
  "endpoint": "CAM DUO2"
}
```

Les valeurs changeantes produites par la supervision vont dans `attributes`, par
exemple l'état, le message d'erreur, la condition en échec ou une métrique.

Si plusieurs endpoints peuvent tomber dans la même fenêtre de grâce, la
corrélation **Agrégée par sujet** permet de n'envoyer qu'un seul job à l'agent
avec les endpoints encore en panne à l'échéance.

Les noms exacts des champs reçus dans l'événement Home Assistant `gatus_alert`
dépendent de ce que publie le fournisseur Gatus. Inspectez d'abord cet événement
dans Home Assistant, puis mappez les champs stables vers `subject` et les champs
variables vers `attributes`.

### Tester un recovery manuellement

Avec un incident de grâce actif, envoyez :

```yaml
action: rest_command.acp_event
data:
  event_type: "service.recovered"
  occurred_at: "{{ utcnow().isoformat() }}"
  idempotency_key: "manual-acp-recovery-001"
  subject:
    service: "acp_manual_test"
  attributes:
    message: "Service rétabli"
    status: "reachable"
```

En corrélation Simple, l'incident entier doit être annulé. En corrélation Agrégée,
seul le sujet exactement correspondant doit être retiré.

---

## 10. Résultats possibles d'un événement

La vue **Événements** montre le résultat de traitement. Les principaux états sont :

| Résultat | Signification |
| --- | --- |
| `accepted` / `queued` | Exécution créée immédiatement |
| `grace_started` | Premier événement : incident de grâce ouvert |
| `grace_active` | Incident Simple déjà actif, dernière entrée actualisée |
| `grace_subject_added` | Nouveau sujet ajouté à un incident agrégé |
| `grace_subject_updated` | Sujet déjà présent, données actualisées |
| `grace_reactivated` | Nouvelle alerte ayant réactivé un incident bloqué |
| `grace_cancelled` | Recovery Simple : incident annulé |
| `subject_recovered` | Recovery agrégé : un sujet retiré |
| `incident_resolved` | Dernier sujet récupéré : incident entièrement résolu |
| `recovery_subject_unknown` | Recovery pour un sujet absent ; aucun autre sujet modifié |
| `recovery_recorded` | Recovery reçu sans incident actif |
| `task_execution_active` | La tâche possède déjà une exécution active |
| `cooldown_active` | Déclencheur encore dans son cooldown |
| `incident_subject_limit` | Limite de 100 sujets atteinte |
| `aggregate_subject_too_large` | `subject` agrégé supérieur à 4096 octets |
| `accepted_after_grace` | Incident promu en exécution après la grâce |

Chaque événement entrant reste conservé individuellement, même lorsqu'il ne crée
pas de job.

---

## 11. Planifications

Une planification crée automatiquement des exécutions d'une tâche prête.

### Nom

Nom humain, par exemple :

```text
Diagnostic quotidien réseau
```

### Tâche

Tâche à exécuter. Elle doit être prête lors de la création ou modification de la
planification.

### Mode Intervalle

Exécute périodiquement la tâche selon la fréquence choisie. L'interface propose
notamment 5, 15, 30, 60, 360, 1440 et 10080 minutes.

Les occurrences manquées pendant un arrêt ne sont pas rejouées en rafale.

### Mode Chaque jour

Paramètres :

- heure locale `HH:MM` ;
- fuseau IANA, par exemple `Europe/Paris`.

Le fuseau est important pour gérer correctement heure d'été/heure d'hiver.

### Mode Chaque semaine

Même principe que le mode quotidien avec en plus le jour de la semaine.

Le modèle interne utilise :

```text
0 = lundi ... 6 = dimanche
```

### Que se passe-t-il si la tâche ne peut pas être lancée ?

La planification ne crée pas un job invalide. Son dernier résultat indique par
exemple :

- `skipped_active` : la même tâche est déjà active ;
- `queue_full` : file pleine ;
- `task_unavailable` : dépendance non prête.

L'occurrence suivante est quand même calculée ; les occurrences manquées ne sont
pas accumulées.

Les planifications internes créent une entrée de tâche vide `{}`.

---

## 12. Exécutions

Une exécution est un job persistant.

### États

| État | Signification |
| --- | --- |
| `queued` | En attente d'un agent |
| `leased` | Réclamée et en cours |
| `completed` | Terminée avec rapport valide |
| `failed` | Échec non réessayable |
| `dead_letter` | Échec réessayable ayant épuisé les tentatives |
| `cancelled` | Annulée par l'administrateur avant réclamation |

### Leases

Lorsqu'un agent réclame un job, ACP lui accorde un lease initial de 5 minutes.
Des heartbeats peuvent l'étendre, sans dépasser 30 minutes depuis la réclamation.
Un lease expiré consomme une tentative ; le job retourne en file ou devient une
dead letter si le nombre maximal est atteint.

Une identité worker ne peut posséder qu'un lease actif à la fois.

### Annuler

Seul un job encore `queued` peut être annulé depuis l'interface.

### Relancer une dead letter

La relance ne réécrit pas l'historique. ACP crée un **nouveau job** à partir de
la dead letter, après avoir revérifié la disponibilité de la tâche, les
connecteurs, les schémas, la concurrence et la capacité de la file.

---

## 13. Rapports

Le rapport final attendu par une tâche est un objet structuré :

```json
{
  "schema_version": 1,
  "summary": "Résumé du diagnostic",
  "findings": [
    "Premier constat",
    "Deuxième constat"
  ]
}
```

Contraintes principales :

- `schema_version` : entier ;
- `summary` : chaîne non vide, maximum 2000 caractères ;
- `findings` : tableau, maximum 100 éléments ;
- aucun champ de premier niveau supplémentaire.

La vue **Rapports** affiche le résumé, les constats et les données brutes.

---

## 14. Audit et rétention

### Chaîne d'audit

Les entrées d'audit sont chaînées par HMAC. ACP maintient un checkpoint
authentifié et effectue :

- une vérification complète au démarrage ;
- une vérification complète au moins toutes les 24 heures ;
- une vérification à la demande via **Vérifier maintenant** ;
- une vérification complète immédiate si une incohérence est détectée pendant
  une progression incrémentale.

Le bouton **Exporter JSONL** télécharge jusqu'aux 10 000 entrées les plus récentes
sous forme de JSON Lines.

### Politique de rétention

Paramètres :

| Paramètre | Effet |
| --- | --- |
| **Conserver les données terminées** | Âge minimum avant suppression des données opérationnelles terminées |
| **Maximum par passage** | Taille maximale du lot de nettoyage |
| **Nettoyage automatique** | Autorise un passage automatique borné au plus une fois toutes les 24 h |

Le contrat technique accepte :

- rétention : 7 à 3650 jours ;
- taille de lot : 10 à 1000.

L'interface propose un sous-ensemble de valeurs courantes.

La rétention peut supprimer les jobs terminaux anciens (`completed`, `failed`,
`cancelled`, `dead_letter`), leurs tentatives, leurs rapports et les événements
orphelins devenus anciens.

Elle ne supprime pas :

- jobs `queued` ou `leased` ;
- configuration ;
- audit ;
- événements encore référencés par un incident actif.

La politique par défaut conserve les données opérationnelles terminées pendant
90 jours.

---

## 15. Dépannage Home Assistant → ACP

### HTTP 401

Cause probable : credential absent, invalide, révoqué ou mal recopié.

Vérifiez :

```yaml
acp_event_authorization: "Bearer ..."
```

et l'en-tête `Authorization` du `rest_command`.

### HTTP 403

L'identité est authentifiée mais ne possède pas `events.create`.

### HTTP 413

Le corps JSON dépasse 32 Kio.

### HTTP 422 `invalid_request`

Causes fréquentes :

- mauvais `Content-Type` ;
- `schema_version` différent de 1 ;
- `event_type` invalide ;
- timestamp sans fuseau horaire ;
- timestamp trop ancien ou trop futur ;
- `Idempotency-Key` absent ou supérieur à 160 caractères ;
- aucun déclencheur actif pour **cette source + ce type** ;
- `subject` vide en corrélation agrégée ;
- tâche ou dépendance devenue indisponible ;
- champ JSON de premier niveau inattendu.

### HTTP 429

La source a dépassé `intake_rate_limit_per_minute`. Le serveur renvoie
`Retry-After: 60`.

### HTTP 503

La file ACP est pleine au moment où l'événement doit créer un job.

### L'événement apparaît mais aucun job n'est créé

Ce n'est pas forcément une erreur. Regardez la colonne **Résultat** dans
**Événements**. Les causes normales incluent :

- incident de grâce actif ;
- recovery ;
- cooldown ;
- tâche déjà active ;
- événement dupliqué par clé d'idempotence.

### Le recovery ne ferme pas le bon incident

En mode **Agrégée par sujet**, comparez le `subject` exact de l'alerte et du
recovery. Ne mettez jamais dans `subject` des valeurs variables comme un message,
un timestamp ou un état.

### Le déclencheur refuse d'être créé

Vérifiez que :

- la source est une identité `event_source` active ;
- la tâche est `ready` ;
- avec grâce, un `recovery_event_type` différent de l'alerte est défini ;
- sans grâce, la corrélation est `simple` et aucun recovery n'est configuré ;
- le même type d'événement n'est pas déjà utilisé par un autre déclencheur de la
  même source.

---

## 16. Sécurité et bonnes pratiques

- publiez `8098` uniquement sur un LAN/VPN de confiance ;
- créez une identité séparée par client ou source ;
- donnez uniquement les permissions nécessaires ;
- utilisez une identité Home Assistant dédiée avec seulement `events.create` ;
- ne stockez pas le credential ACP en clair dans `configuration.yaml` ;
- utilisez `secrets.yaml` et protégez également vos sauvegardes ;
- sélectionnez le minimum d'outils MCP nécessaire par tâche ;
- utilisez les arguments fixes pour retirer à l'agent les paramètres qu'il ne
  doit pas pouvoir modifier ;
- classez comme `fixed_sensitive` les valeurs fixes confidentielles ;
- ne mettez pas de secret dans `subject`, `attributes`, les instructions de tâche
  ou les valeurs ordinaires ;
- vérifiez régulièrement l'état de la chaîne d'audit.

ACP ne repose pas sur une seconde approbation transactionnelle : la sélection et
la configuration explicites de l'administrateur définissent la politique. Tout ce
qui sort de cette enveloppe est refusé.

---

## 17. Données, sauvegarde et mises à niveau

La configuration, la file, les rapports, les événements et l'audit sont stockés
dans le volume de données de l'App et couverts par les sauvegardes froides Home
Assistant.

Depuis les installations existantes en `0.46.8`, les données persistantes sont
considérées comme non jetables. Toute évolution incompatible du schéma SQLite
doit fournir un chemin de migration explicite et testé. Supprimer les données de
l'App et réinstaller proprement n'est plus une stratégie normale de mise à jour.

Si une base ne peut pas être mise à niveau de façon sûre, le démarrage doit
échouer en mode fermé sans modification partielle et la version doit documenter
le chemin de sauvegarde/récupération nécessaire.

---

## 18. Faux serveur MCP de test

Le dépôt fournit `scripts/fake_mcp_server.py`, un serveur Streamable HTTP de
recette en lecture seule. Il permet notamment de tester la découverte et les
collisions de noms d'outils.

```bash
python3 -m pip install 'mcp==1.28.1'
python3 agent_control_plane/scripts/fake_mcp_server.py --host 0.0.0.0 --port 8765
```

Arrêtez le serveur et retirez toute règle temporaire de pare-feu après le test.

---

## 19. Limites connues

- Streamable HTTP est le seul transport de connecteur pris en charge ;
- les connecteurs `stdio` et le SSE historique ne sont pas pris en charge ;
- ACP ne proxifie que les outils MCP, pas les resources/prompts/roots/sampling ;
- aucun worker autonome n'est embarqué : un client MCP externe traite la file ;
- le déploiement multi-instance / haute disponibilité n'est pas pris en charge ;
- l'exposition directe sur Internet n'est pas prise en charge ;
- les planifications internes n'acceptent actuellement pas de payload d'entrée
  personnalisé et créent une entrée `{}`.

Pour les détails du protocole et des schémas pris en charge, voir
[MCP_COMPATIBILITY.md](MCP_COMPATIBILITY.md).

## 20. Parcours opérationnels actuels

### Activité et maintenance des connecteurs

**Activité** est un journal persistant sans payload adossé à la chaîne d’audit ACP. Il conserve des métadonnées bornées pour l’administration, l’orchestration, la sécurité et le cycle de vie, notamment `app_started`, `app_ready` et `app_stopped`. Il ne stocke jamais corps d’événement, URL de connecteur, Bearer, valeur fixe sensible, argument/résultat, prompt ou rapport.

La modification ordinaire d’un connecteur conserve son Bearer protégé. Remplacement d’endpoint et rotation du secret restent deux opérations explicites distinctes :

1. terminez toute exécution dépendante ;
2. utilisez **Modifier** pour le nom et, uniquement si nécessaire, l’endpoint ;
3. utilisez **Rotation du secret** seulement pour remplacer le Bearer ;
4. laissez ACP reconnecter, valider les schémas et actualiser l’inventaire avant validation.

ACP refuse ces changements pendant une exécution dépendante. Une validation échouée conserve l’ancien inventaire mais ferme les chemins dépendants, sans retourner l’ancien endpoint ou secret au navigateur.

### Exemples JSON d’arguments fixes

Pour un schéma amont comme :

```json
{
  "type": "object",
  "properties": {
    "entity_id": {"type": "string"},
    "action": {"type": "string", "enum": ["turn_on", "turn_off"]},
    "authorization": {"type": "string"}
  },
  "required": ["entity_id", "action", "authorization"],
  "additionalProperties": false
}
```

Laissez `action` modifiable par l’agent, saisissez `entity_id` comme valeur fixe ordinaire JSON valide :

```json
"light.office"
```

et `authorization` comme valeur fixe sensible JSON valide :

```json
"Bearer REMPLACER_PAR_LE_TOKEN_CIBLE"
```

Une chaîne exige ses guillemets JSON, contrairement à un nombre. Une structure est saisie comme valeur JSON complète :

```json
{"site":"principal","scope":["read","status"]}
```

ACP retire les propriétés fixes du schéma visible par le modèle, les injecte côté serveur, valide l’appel fusionné, chiffre les valeurs sensibles au repos et les expurge récursivement des résultats amont.

### Connecter un worker AEP

1. Créez une identité **Client MCP** dédiée au rôle de worker, avec uniquement `jobs.claim`, `jobs.heartbeat`, `jobs.complete` et `jobs.fail` ; ce sont ces permissions qui définissent ce rôle.
2. Copiez son credential affiché une seule fois.
3. Dans **Control Plane** d’AEP, configurez `http://IP_HOME_ASSISTANT:PORT_ACP/mcp` et collez ce credential.
4. Vérifiez qu’AEP annonce une connexion validée et des polls réussis.

ACP reste l’autorité sur la révision de tâche, les empreintes connecteur/schéma, les arguments fixes, l’autorisation, les retries, le lease et le contrat de rapport. AEP reçoit uniquement `allowed_capabilities` effectif et ne choisit jamais d’outils supplémentaires dans l’inventaire.

Le listener public MCP/événements utilise actuellement HTTP. Les Bearers authentifient mais ne chiffrent pas le transport. Conservez `8098` sur un chemin HAOS/LAN de confiance ou placez un reverse proxy TLS fiable devant lui ; ne l’exposez jamais directement à un réseau non fiable.
