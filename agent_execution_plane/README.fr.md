# Agent Execution Plane

Agent Execution Plane est le composant de raisonnement et d’exécution de modèles de la suite. La version `0.3.0` étend le Lot 1 avec OpenAI ChatGPT OAuth officiel tout en conservant le shell HAOS Lot 0 accepté.

## Installation et utilisation

Ajoutez ce dépôt au magasin d’Apps Home Assistant, installez **Agent Execution Plane**, démarrez l’App puis ouvrez son panneau Ingress. Le listener d’administration est accessible uniquement via Ingress sur le port conteneur `8099`. Le port conteneur `8098` est la future surface API autonome ; dans le Lot 0, il expose uniquement `/health/live` et `/health/ready`. Son port hôte peut être choisi dans les paramètres Réseau de l’App ou laissé désactivé.

Le header Ingress propose les contrôles visibles FR/EN et clair/sombre. Au premier usage, la langue suit la préférence du navigateur lorsqu’elle est prise en charge, sinon le français est utilisé ; le thème suit la préférence du navigateur. Les choix manuels sont mémorisés uniquement dans le stockage local du navigateur.

La vue Activité conserve les métadonnées opérationnelles sûres pendant 30 jours ou 10 000 entrées, selon la première limite atteinte. Elle ne stocke jamais de prompts, résultats, identifiants, corps de requête, raisonnement ou payloads d’outils.

La vue Modèles gère les endpoints Ollama-compatible et OpenAI-compatible, la priorité déterministe, l’activation, les timeouts positifs et les credentials provider optionnels chiffrés. La validation explicite OpenAI-compatible effectue un petit probe tool-call pouvant consommer de l’usage provider. Le health automatique au démarrage n’effectue jamais d’inférence.

OpenAI ChatGPT OAuth utilise l’app-server Codex officiel exactement pinné en `0.144.4` et une connexion ChatGPT device-code partagée. Cette famille n’accepte ni URL de base ni clé API ; Codex reste seul propriétaire de la persistance et du refresh OAuth sous `/data/private/codex-home`.

Le Lot 1 ne fournit volontairement aucune soumission d’exécution, polling ACP, moteur d’exécution ou boucle MCP. See [README.md](README.md) for English documentation.
