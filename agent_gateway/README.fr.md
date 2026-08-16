# Agent Gateway

Agent Gateway est une App Home Assistant stable qui sert d’intermédiaire
entre des agents authentifiés et un ou plusieurs serveurs MCP externes. Elle
n’expose que les outils virtuels sélectionnés pour une tâche, conserve les
identifiants des serveurs en amont dans la passerelle, met les exécutions en file
de façon persistante et stocke des rapports structurés ainsi qu’un journal
d’audit append-only.

Elle fonctionne comme un pare-feu applicatif générique pour MCP : deny-by-default,
la configuration explicite de l’administrateur constitue l’autorisation. Un outil
découvert mais non sélectionné reste inutilisable ; un outil explicitement
sélectionné dans une tâche valide est autorisé uniquement dans l’enveloppe exacte
de cette tâche, de sa révision, de l’identité, du schéma effectif et des éventuelles
restrictions d’arguments. Agent Gateway ne crée pas de classe d’autorisation
séparée selon qu’un outil est présenté comme lecture, écriture ou administration.

Documentation anglaise : [README.md](README.md).

## Fonctionnalités actuelles

- connecteurs MCP Streamable HTTP génériques, avec authentification Bearer
  facultative ;
- inventaire indépendant par connecteur et noms d’outils virtuels sans collision ;
- tâches composées d’outils choisis dans un ou plusieurs connecteurs ;
- restrictions facultatives `fixed_arguments_v1` par outil, qui retirent des
  arguments de premier niveau du schéma visible par l’agent et injectent dans
  la passerelle leur valeur fixe ordinaire ou sensible protégée ;
- clients MCP et sources d’événements authentifiés ;
- exécutions manuelles, planifiées ou déclenchées par événement ;
- cooldown et incidents de grâce durables par déclencheur, avec rétablissement
  global simple ou agrégation bornée et rétablissement par sujet stable ;
- leases persistants, nouvelles tentatives, dead letters et rapports lisibles ;
- archivage réversible des tâches et connecteurs sans supprimer l’historique ;
- rétention bornée et vérification de la chaîne d’audit append-only ;
- interface Ingress française et anglaise avec cockpit opérationnel, panneaux
  de configuration séparés, détection du navigateur et sélecteur mémorisé ;
- métriques opérationnelles agrégées, sans secret ni label à forte cardinalité.

Agent Gateway n’intègre pas de modèle et n’exécute pas seul un agent. Un client
compatible MCP comme Codex réclame les travaux en attente, appelle les outils
virtuels publiés pour la tâche réclamée, puis soumet le rapport final.

## Installation

1. Ajouter ce dépôt à la boutique d’Apps Home Assistant.
2. Installer **Agent Gateway**.
3. Ne pas publier le port TCP `8098` tant qu’un client MCP ou une source
   d’événements n’en a pas besoin.
4. Démarrer l’App et ouvrir son interface Ingress.

L’administration est accessible uniquement par l’Ingress authentifié de Home
Assistant. Le port `8098` transporte l’API MCP et événements authentifiée ; ne
l’exposer que sur un LAN ou VPN de confiance.

## Premier workflow

1. Dans **Connecteurs**, saisir un nom et l’URL Streamable HTTP `/mcp`, puis
   cliquer sur **Tester et ajouter**.
2. Dans **Tâches**, écrire les instructions transmises à l’agent et sélectionner
   uniquement les outils nécessaires à cette tâche. Conserver le mode
   **Standard**, ou déplier **Restreindre cet outil** pour configurer un appel
   exemple valide et classer certains arguments de premier niveau comme
   modifiables par l’agent, fixes ordinaires ou fixes sensibles.
3. Dans **Identités**, créer une identité Client MCP avec les permissions
   de traitement et de rapport, puis copier son identifiant affiché une fois.
4. Configurer le client MCP avec `http://IP_HOME_ASSISTANT:8098/mcp` et envoyer
   cet identifiant comme jeton Bearer.
5. Lancer la tâche manuellement, la planifier ou créer une source d’événements
   authentifiée et un déclencheur.
6. Contrôler **Exécutions**, **Rapports** et **Audit**.

## Cycle de vie des connecteurs et tâches

La désactivation est temporaire. L’archivage retire une ressource des vues
opérationnelles normales tout en conservant ses exécutions, rapports et entrées
d’audit. Une ressource restaurée reste désactivée jusqu’à sa réactivation
explicite. Agent Gateway refuse l’archivage tant qu’un travail associé est en
attente ou loué. Archiver une tâche met aussi en pause ses planifications et ses
déclencheurs.

## Langue

Au premier affichage, l’interface suit la préférence `fr` ou `en` du navigateur
et utilise le français comme repli. Le bouton **FR/EN** mémorise uniquement le
choix d’affichage dans ce navigateur et ne modifie aucune donnée. Les noms MCP,
identifiants techniques et données provenant des systèmes restent inchangés.

## Données, sauvegarde et rétention

La configuration, la file, les rapports et l’audit sont stockés dans le volume
de données de l’App et inclus dans les sauvegardes froides Home Assistant. La
rétention conserve par défaut les données opérationnelles terminées pendant 90
jours. Les travaux en attente ou loués, la configuration et l’audit ne sont
jamais supprimés par cette rétention.

Pendant la phase actuelle de développement avec un seul testeur, les versions
qui changent le schéma imposent la suppression des données de l’App et une
réinstallation propre ; elles n’embarquent pas de migrations destinées à des
données jetables. Une génération inconnue est refusée avec une demande claire
de réinstallation. Une politique de préservation sera introduite seulement
lorsque de vraies données non jetables existeront. Aucun export ou import de
configuration séparé n’est prévu tant que les sauvegardes Home Assistant
couvrent la restauration cohérente.

## Incidents de grâce et corrélation des sujets

Un déclencheur avec délai de grâce propose une corrélation **Simple** ou
**Agrégée par sujet**. Le mode agrégé exige que chaque alerte et chaque
rétablissement portent le même objet `subject`, stable et non vide, pour une
ressource. Les observations variables vont dans `attributes`. La première
alerte fixe l’échéance ; les sujets suivants ne la prolongent pas. Un
rétablissement retire uniquement le sujet correspondant et, à l’échéance, un
seul travail est créé avec tous les sujets encore actifs.

Les incidents et leur nombre de sujets restent visibles dans
**Déclencheurs**. Leur promotion est atomique et bornée. Un incident impossible
à mettre en file après le nombre maximal de tentatives devient visiblement
bloqué et peut être relancé par un administrateur. Chaque événement entrant
reste conservé individuellement et audité.

## Frontières de sécurité

- les listeners tournent sous un utilisateur non privilégié avec AppArmor ;
- l’administration est isolée du listener public MCP/événements ;
- la découverte d’un outil n’accorde aucun droit d’exécution ;
- seuls les outils explicitement sélectionnés dans la révision de tâche valide
  sont exposés et invocables par l’identité autorisée ;
- la sélection explicite d’un outil par l’administrateur constitue son
  autorisation, indépendamment d’une éventuelle étiquette sémantique lecture,
  écriture ou administration ;
- tout outil ou argument situé hors de l’enveloppe configurée est refusé ;
- les secrets des connecteurs sont chiffrés et ne sont jamais transmis aux agents ;
- les arguments fixes sensibles sont chiffrés au repos puis expurgés par nom de
  clé et par valeur transitoire de toute réponse amont avant remise à un agent ;
- les arguments fixes sont absents du schéma virtuel, impossibles à remplacer
  par l’agent et injectés seulement après validation de l’appel réduit ;
- les schémas d’entrée MCP admis utilisent JSON Schema Draft 2020-12 et sont
  intégralement appliqués avant tout appel amont ; contrainte, format, dialecte
  inconnu ou référence externe provoque un refus fermé ;
- un connecteur joignable dont le schéma ne peut pas être admis passe à l’état
  `invalid` avec son `last_error_code` précis, tandis qu’une panne de transport
  reste `unreachable` ;
- chaque appel est résolu par révision de tâche, connecteur, outil et empreinte
  de schéma ;
- un agent ne reçoit ni le secret original ni l’inventaire complet d’un connecteur ;
- les entrées d’audit sont chaînées par HMAC et vérifiables dans l’interface ;
- le cockpit ne parcourt jamais la chaîne : il lit un état borné, tandis que
  l’ancre authentifiée est revalidée avant chaque progression incrémentale ;
- un contrôle intégral s’exécute au démarrage, toutes les 24 heures, sur demande
  et immédiatement après toute incohérence, sans écraser le dernier checkpoint
  valide lorsqu’il échoue.

Le modèle de sécurité ne repose pas sur une seconde approbation transactionnelle :
la passerelle applique strictement la politique explicitement configurée par
l’administrateur et échoue en mode fermé dès qu’elle ne peut plus prouver que
l’appel reste dans cette enveloppe.

## Faux serveur MCP de test

`scripts/fake_mcp_server.py` est un serveur de recette inoffensif et en lecture
seule. Son faux outil `ha_get_addon` démontre que deux connecteurs peuvent
publier le même nom en amont tout en recevant deux noms virtuels uniques.

```bash
python3 -m pip install 'mcp==1.28.1'
python3 agent_gateway/scripts/fake_mcp_server.py --host 0.0.0.0 --port 8765
```

Arrêter le serveur et retirer toute règle temporaire de pare-feu après le test.

## Limites connues

- Streamable HTTP est le seul transport de connecteur pris en charge ;
- aucun worker autonome n’est fourni : un client MCP externe traite la file ;
- le déploiement multi-instance ou haute disponibilité n’est pas pris en charge ;
- l’exposition directe sur Internet n’est pas prise en charge ; utiliser un LAN
  ou VPN de confiance.
