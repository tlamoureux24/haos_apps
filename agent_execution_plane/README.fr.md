# Agent Execution Plane

Agent Execution Plane est le composant de raisonnement et d’exécution de modèles de la suite. La version `0.1.0` implémente uniquement le shell exécutable HAOS du Lot 0 : listeners sécurisés, administration Ingress, contrôles de santé, plomberie SQLite génération 1 et journal d’activité persistant sûr.

## Installation et utilisation

Ajoutez ce dépôt au magasin d’Apps Home Assistant, installez **Agent Execution Plane**, démarrez l’App puis ouvrez son panneau Ingress. Le listener d’administration est accessible uniquement via Ingress sur le port conteneur `8099`. Le port conteneur `8098` est la future surface API autonome ; dans le Lot 0, il expose uniquement `/health/live` et `/health/ready`. Son port hôte peut être choisi dans les paramètres Réseau de l’App ou laissé désactivé.

Le header Ingress propose les contrôles visibles FR/EN et clair/sombre. Au premier usage, la langue suit la préférence du navigateur lorsqu’elle est prise en charge, sinon le français est utilisé ; le thème suit la préférence du navigateur. Les choix manuels sont mémorisés uniquement dans le stockage local du navigateur.

La vue Activité conserve les métadonnées opérationnelles sûres pendant 30 jours ou 10 000 entrées, selon la première limite atteinte. Elle ne stocke jamais de prompts, résultats, identifiants, corps de requête, raisonnement ou payloads d’outils.

Le Lot 0 ne fournit volontairement aucun provider de modèle, soumission d’exécution, polling ACP ou boucle MCP. See [README.md](README.md) for English documentation.
