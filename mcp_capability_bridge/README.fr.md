# MCP Capability Bridge

Français | [English](README.md)

Version actuelle : **0.4.5 — micro-lot UX des clés techniques générées, en attente de recette HAOS**.

MCP Capability Bridge sera une App Home Assistant OS autonome transformant des accès techniques non-MCP, délibérément bornés, en outils MCP Streamable HTTP standards.

Les premiers adaptateurs intégrés seront :

- des capacités SSH bornées définies par l’administrateur, avec une nouvelle connexion vérifiée à chaque appel ;
- des sessions Web interactives de courte durée dont l’autorité réelle correspond exactement aux droits du compte configuré sur la cible.

Plusieurs clients MCP seront pris en charge grâce à des namespaces isolés. Chaque namespace possédera son propre credential Bearer affiché une seule fois, son inventaire d’outils publié, ses quotas et ses sessions Web. Agent Control Plane pourra se connecter comme un client ordinaire puis restreindre ces outils pour chaque tâche ; Agent Execution Plane les recevra par la frontière MCP générique existante d’ACP. Aucun de ces composants ne sera nécessaire au fonctionnement autonome.

L’administration sera accessible uniquement par Home Assistant Ingress et reprendra les conventions visuelles et ergonomiques d’ACP/AEP : français/anglais, clair/sombre, actions principales en haut à droite, drawers latéraux accessibles, géométrie stable des barres de défilement et responsive mobile.

Documents de conception normatifs :

- [Cadrage produit](PROJECT_BRIEF.md)
- [Conception technique](TECHNICAL_DESIGN.md)
- [Modèle de menaces](THREAT_MODEL.md)
- [Plan d’implémentation](IMPLEMENTATION_PLAN.md)

La version 0.4.0 ajoute le runtime Chromium jetable et confiné ainsi que la configuration statique des cibles Web. Aucun outil MCP Web n’est encore exposé. Consultez les [instructions d’installation et de recette](DOCS.md).
