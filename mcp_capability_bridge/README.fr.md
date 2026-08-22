# MCP Capability Bridge

Français | [English](README.md)

Version actuelle : **1.0.0 stable — Lots 0 à 4 acceptés sur HAOS réel**.

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

La version 1.0.0 est la livraison stable du Lot 4 après validation HAOS de l’installation, de la persistance, de la sauvegarde/restauration, de l’endurance et d’AppArmor. La génération SQLite 1 devient le cutoff de compatibilité des données de production. Consultez les [instructions d’installation et d’intégration](DOCS.md).
