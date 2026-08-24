# MCP Capability Bridge

Français | [English](README.md)

MCP Capability Bridge est une App Home Assistant OS autonome transformant des accès techniques non-MCP, délibérément bornés, en outils MCP Streamable HTTP standards.

Les adaptateurs intégrés sont :

- des capacités SSH bornées définies par l’administrateur, avec une nouvelle connexion vérifiée à chaque appel ;
- des sessions Web interactives de courte durée dont l’autorité réelle correspond exactement aux droits du compte configuré sur la cible.

Plusieurs clients MCP sont pris en charge grâce à des namespaces isolés. Chaque namespace possède son propre credential Bearer affiché une seule fois, son inventaire d’outils publié, ses quotas et ses sessions Web. Agent Control Plane peut se connecter comme un client ordinaire puis restreindre ces outils pour chaque tâche ; Agent Execution Plane les reçoit par la frontière MCP générique existante d’ACP. Aucun de ces composants n’est nécessaire au fonctionnement autonome.

L’administration est accessible uniquement par Home Assistant Ingress et reprend les conventions visuelles et ergonomiques d’ACP/AEP : français/anglais, clair/sombre, actions principales en haut à droite, drawers latéraux accessibles, géométrie stable des barres de défilement et responsive mobile.

Documents de conception normatifs :

- [Cadrage produit](PROJECT_BRIEF.md)
- [Conception technique](TECHNICAL_DESIGN.md)
- [Modèle de menaces](THREAT_MODEL.md)
- [Plan d’implémentation](IMPLEMENTATION_PLAN.md)
- [Guide d’exploitation TLS](../TLS.md)

Home Assistant affiche le numéro de version directement depuis `config.yaml`;
ce README ne le duplique volontairement pas. Le runtime a passé les recettes
HAOS réelles d’installation, persistance, sauvegarde/restauration, endurance,
TLS et AppArmor. La génération SQLite 1 est le cutoff de compatibilité des
données de production. Consultez les
[instructions d’installation et d’intégration](DOCS.md).

## Installation et modèle réseau

L’administration est disponible uniquement par Home Assistant Ingress sur le port interne `8099`. Le mapping facultatif de `8098/tcp` expose seulement les healthchecks publics et MCP Streamable HTTP authentifié sur `/mcp`.

```text
Ingress 8099 : administration uniquement
Public  8098 : /health/live, /health/ready, /mcp
```

Ne publiez pas `8098` si aucun client MCP ne doit joindre le Bridge. HTTPS avec
un certificat autogénéré persistant est le mode par défaut. L’administration et
les logs affichent son empreinte SHA-256 pour vérification indépendante et
épinglage. Un certificat externe peut être chargé depuis `/ssl`. HTTP reste
disponible, mais il est non chiffré et produit un avertissement anglais.

Pour TLS externe, saisissez des noms relatifs à `/ssl`, par exemple
`agent-suite-cert.pem` et `agent-suite-key.pem`, jamais des chemins absolus. La
page **Transport & TLS** indique l’état du listener et les détails du
certificat. Le [guide TLS bilingue](../TLS.md) couvre la génération OpenSSL, les
permissions, l’épinglage, la rotation, la sauvegarde et le confinement des
pannes.

| Option de l’App | Valeurs | Défaut | Explication |
|---|---|---|---|
| `public_transport` | `http`, `https` | `https` | Transport MCP public |
| `certificate_source` | `self_generated`, `external` | `self_generated` | Source du certificat HTTPS |
| `certfile` | nom de fichier | vide | Certificat externe, relatif à `/ssl` |
| `keyfile` | nom de fichier | vide | Clé privée externe, relative à `/ssl` |

## Clients MCP et isolation des namespaces

1. Ouvrez **Clients MCP** et créez un client avec un nom clair.
2. Copiez immédiatement le credential généré ; il ne sera plus affichable.
3. Créez les cibles et capacités bornées.
4. Dans **Accès MCP**, publiez explicitement chaque capacité nécessaire à ce client.

Chaque client voit uniquement son inventaire publié. La rotation invalide immédiatement l’ancien credential et ferme les sessions Web de ce client. La révocation bloque l’accès et doit précéder l’archivage. Les clés techniques sont générées automatiquement, stables et seulement présentées comme identifiants opérationnels.

Connexion d’un client générique :

```text
URL : https://IP_HOME_ASSISTANT:PORT_BRIDGE/mcp
En-tête : Authorization: Bearer REMPLACER_PAR_LE_CREDENTIAL_CLIENT
```

## Cibles SSH

Utilisez un compte dédié au moindre privilège. Le Bridge crée une nouvelle connexion SSH par appel et interdit PTY, agent SSH, forwarding, stdin, environnement contrôlé par l’appelant et commande libre.

### Créer et épingler une cible

1. Renseignez hôte/IP, port, utilisateur et authentification par mot de passe ou clé privée.
2. Cliquez sur **Scanner la clé d’hôte**.
3. Comparez indépendamment l’empreinte affichée à une valeur fiable fournie par l’administrateur de la cible.
4. Confirmez uniquement après cette comparaison.

La clé épinglée est vérifiée à chaque connexion. Si elle change légitimement, utilisez la rotation explicite et contrôlez à nouveau la nouvelle empreinte.

### Définir une capacité SSH bornée

L’exécutable doit être absolu. Le template est un tableau JSON contenant soit un `literal` fixe, soit un `parameter` nommé. Chaque paramètre devient un unique token shell correctement cité, jamais une chaîne de commande.

Exemple pour lire l’état d’un service systemd :

```text
Exécutable : /usr/bin/systemctl
```

```json
[
  {"literal": "status"},
  {"parameter": "unit"},
  {"literal": "--no-pager"}
]
```

Schéma d’entrée :

```json
{
  "type": "object",
  "properties": {
    "unit": {
      "type": "string",
      "enum": ["nginx.service", "docker.service"]
    }
  },
  "required": ["unit"],
  "additionalProperties": false
}
```

La commande produite est exactement `/usr/bin/systemctl status <unité-validée> --no-pager`. Préférez `enum`, `const`, les patterns et limites numériques à une chaîne trop large. Configurez un timeout court et des limites stdout/stderr réalistes. Cochez **Effet possible** dès que la commande modifie un état ; une réponse perdue devient alors ambiguë et ne doit pas provoquer de retry automatique.

Commande fixe en lecture seule :

```json
[
  {"literal": "--version"}
]
```

```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```

Après enregistrement, publiez l’outil `ssh_<clé-technique>` uniquement aux clients nécessaires.

## Cibles et sessions Web

L’automatisation Web utilise un profil Chromium neuf et jetable. Son autorité réelle est exactement celle du compte Web configuré : utilisez donc un compte dédié avec le rôle minimal.

1. Saisissez l’origine exacte, par exemple `https://routeur.example.local`, et non une URL de navigation arbitraire.
2. Résolvez-la dans l’interface et confirmez les adresses attendues. Un changement échoue fermé comme risque de DNS rebinding.
3. Gardez la vérification TLS active sauf exception locale étroitement comprise.
4. Choisissez aucune authentification, HTTP Basic ou formulaire borné configuré.
5. Définissez les durées d’inactivité et absolue, puis lancez **Tester le navigateur**.
6. Publiez uniquement les outils Web nécessaires.

Pour un formulaire, les sélecteurs appartiennent à la configuration administrateur et ne sont jamais des arguments MCP :

```text
Chemin de connexion : /login
Sélecteur utilisateur : input[name="username"]
Sélecteur mot de passe : input[name="password"]
Sélecteur validation : button[type="submit"]
```

Les neuf outils bornés sont `open`, `snapshot`, `wait`, `navigate`, `click`, `fill`, `select`, `press` et `close`. Séquence typique :

```json
{"name":"web_routeur_open","arguments":{}}
```

```json
{"name":"web_routeur_snapshot","arguments":{"session":"SESSION_HANDLE"}}
```

```json
{"name":"web_routeur_click","arguments":{"session":"SESSION_HANDLE","reference":"OPAQUE_REFERENCE"}}
```

Les références proviennent uniquement du dernier snapshot d’accessibilité. Chaque tentative d’action invalide toute la génération : prenez un nouveau snapshot avant l’action suivante. Handles et références sont liés au client, à la génération du credential, à la cible, à la session et à la page courante.

Le Bridge refuse URL arbitraires, sélecteurs fournis par le client, JavaScript, champs password/hidden/file, uploads, téléchargements et touches non prévues. `navigate` accepte seulement un chemin relatif sur l’origine approuvée. Les sessions ferment sur close, inactivité, durée maximale, rotation/révocation, erreur ou arrêt de l’App et ne survivent jamais à un redémarrage ou une sauvegarde.

## Exemples d’intégration

### Bridge → ACP → AEP

1. Créez un client Bridge dédié à ACP.
2. Publiez seulement les capacités que doit découvrir ACP.
3. Dans **Connecteurs** d’ACP, ajoutez l’URL `/mcp` du Bridge et ce Bearer.
4. Dans une tâche ACP, sélectionnez uniquement les outils requis et fixez éventuellement les arguments sensibles côté serveur.
5. AEP reçoit seulement l’enveloppe effective finale produite par ACP.

### AEP autonome → Bridge

Dans la requête AEP, fournissez l’endpoint Bridge et le credential d’un client Bridge dédié. Copiez depuis la découverte MCP le nom exact, la description et `input_schema` dans `mcp.tools`. Ne simplifiez pas manuellement le schéma : AEP contrôle sa compatibilité exacte.

## Outcomes, capacité et dépannage

Le Bridge ne rejoue jamais automatiquement une opération SSH ou Web. Si une erreur contient `effect_possible: true`, la cible a pu appliquer l’action malgré la perte de réponse.

Les limites globales, namespace, adaptateur et cible répondent immédiatement `*_busy` sans file cachée. Les corps MCP dépassant 256 Kio sont refusés avant buffering protocolaire.

| Symptôme | Vérification |
|---|---|
| `401` sur `/mcp` | Credential du bon namespace, non renouvelé/révoqué/archivé |
| Outil absent | Capacité active et explicitement publiée à ce namespace |
| Refus de clé SSH | Comparer l’empreinte fiable ; rotation seulement après vérification indépendante |
| Argument SSH refusé | JSON valide, noms exacts, type/enum/pattern du schéma |
| Résolution Web changée | Résoudre à nouveau, analyser le changement, puis confirmer explicitement |
| Session navigateur en échec | Passer temporairement en DEBUG et lire les entrées nettoyées `MCB_BROWSER_DIAG` |
| Référence Web périmée | Reprendre un snapshot ; les références ne valent qu’une génération |

Activité conserve uniquement des métadonnées bornées : client, outil, adaptateur, outcome, source et durée. Credentials, arguments, résultats, contenu Web et sortie SSH n’y sont jamais stockés.
