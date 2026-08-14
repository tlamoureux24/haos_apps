# Agent Gateway

Agent Gateway est une App Home Assistant expérimentale qui sert d’intermédiaire
entre des agents authentifiés et un ou plusieurs serveurs MCP externes. Elle
n’expose que les outils virtuels sélectionnés pour une tâche, conserve les
identifiants des serveurs en amont dans la passerelle, met les exécutions en file
de façon persistante et stocke des rapports structurés ainsi qu’un journal
d’audit append-only.

Documentation anglaise : [README.md](README.md).

## Fonctionnalités actuelles

- connecteurs MCP Streamable HTTP génériques, avec authentification Bearer
  facultative ;
- inventaire indépendant par connecteur et noms d’outils virtuels sans collision ;
- tâches composées d’outils choisis dans un ou plusieurs connecteurs ;
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
   uniquement les outils nécessaires à cette tâche.
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
- les secrets des connecteurs sont chiffrés et ne sont jamais transmis aux agents ;
- chaque appel est résolu par révision de tâche, connecteur, outil et empreinte
  de schéma ;
- un agent ne reçoit ni le secret original ni l’inventaire complet d’un connecteur ;
- les entrées d’audit sont chaînées par hachage et vérifiables dans l’interface.

Les opérations correctives ou en écriture restent différées jusqu’à une revue
de menace, des approbations explicites et des règles qui échouent de façon sûre.

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
- les approbations d’opérations en écriture ne sont pas encore implémentées ;
- le déploiement multi-instance ou haute disponibilité n’est pas pris en charge ;
- l’App reste expérimentale et ne doit pas être exposée sur Internet.
