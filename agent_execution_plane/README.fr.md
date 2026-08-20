# Agent Execution Plane

Agent Execution Plane est le composant de raisonnement et d’exécution de modèles de la suite. La version `0.4.2` contient le moteur interne source-neutre revu, la boucle exacte d’outils MCP opérationnels fournis par la source, la frontière de fallback et les trois familles de providers d’exécution. Les frontières publiques autonome et ACP restent réservées aux lots suivants.

## Frontière de responsabilité

Agent Execution Plane est **uniquement un plan d’exécution**. Il ne possède ni la politique de tâche, ni la configuration des connecteurs MCP, ni la sélection des capacités opérationnelles, ni l’autorisation opérationnelle.

Lorsque Agent Control Plane est utilisé, ACP reste l’unique autorité pour la gouvernance du travail et des capacités opérationnelles. ACP possède les connecteurs MCP amont, la sélection administrateur des outils de tâche, la construction des capacités virtuelles, les schémas effectifs et restrictions comme `fixed_arguments_v1`, l’autorisation et la résolution fail-closed jusqu’à l’appel amont.

Un job ACP réclamé fournit une enveloppe `allowed_capabilities` autoritaire pour les **capacités opérationnelles MCP**. AEP peut vérifier que ces capacités sont toujours techniquement présentes avec les schémas effectifs attendus, mais il ne doit jamais dériver une autre liste de capacités MCP à partir de l’inventaire complet retourné par `tools/list`.

La surface MCP d’ACP contient aussi des opérations de cycle de vie utilisées par la frontière AEP elle-même, par exemple claim, heartbeat, complete et fail. Ces outils de cycle de vie **ne sont pas des outils du modèle de raisonnement** simplement parce que l’identité worker peut les appeler.

Les aides natives du provider dédiées au raisonnement ou à l’information constituent une catégorie séparée. Le modèle/runtime peut utiliser des aides comme la planification interne ou la recherche Web publique tant qu’elles restent dans le domaine de raisonnement du provider et ne permettent pas d’agir sur l’infrastructure de l’utilisateur, d’accéder à l’état privé de l’hôte AEP, d’obtenir des credentials de connecteurs ou de contourner le chemin MCP autorisé par la source.

Conceptuellement :

`gouvernance ACP/source -> enveloppe exacte des capacités opérationnelles MCP -> raisonnement/exécution AEP (+ aides natives provider autorisées) -> résultat -> source`

En mode standalone, le caller est l’autorité source et doit fournir l’enveloppe MCP opérationnelle exacte qui sera invocable par le modèle pour cette exécution. AEP ne construit toujours pas de politique d’autorisation à partir de la découverte MCP.

## Installation et utilisation

Ajoutez ce dépôt au magasin d’Apps Home Assistant, installez **Agent Execution Plane**, démarrez l’App puis ouvrez son panneau Ingress. Le listener d’administration est accessible uniquement via Ingress sur le port conteneur `8099`. Le port conteneur `8098` est la future surface API autonome ; actuellement il expose uniquement `/health/live` et `/health/ready`. Son port hôte peut être choisi dans les paramètres Réseau de l’App ou laissé désactivé.

Le header Ingress propose les contrôles visibles FR/EN et clair/sombre. Au premier usage, la langue suit la préférence du navigateur lorsqu’elle est prise en charge, sinon le français est utilisé ; le thème suit la préférence du navigateur. Les choix manuels sont mémorisés uniquement dans le stockage local du navigateur.

La vue Activité conserve les métadonnées opérationnelles sûres pendant 30 jours ou 10 000 entrées, selon la première limite atteinte. Elle ne stocke jamais de prompts, résultats, identifiants, corps de requête, raisonnement ou payloads d’outils.

La vue Modèles gère les endpoints Ollama-compatible et OpenAI-compatible, la priorité déterministe, l’activation, les timeouts positifs et les credentials provider optionnels chiffrés. La validation explicite OpenAI-compatible effectue un petit probe tool-call pouvant consommer de l’usage provider. Le health automatique au démarrage n’effectue jamais d’inférence.

OpenAI ChatGPT OAuth utilise l’app-server Codex officiel exactement pinné en `0.144.4` et une connexion ChatGPT device-code partagée. Cette famille n’accepte ni URL de base ni clé API ; Codex reste seul propriétaire de la persistance et du refresh OAuth sous `/data/private/codex-home`.

Le Lot 2 ne fournit volontairement aucune soumission d’exécution publique ni polling ACP. Il ajoute uniquement le moteur d’exécution source-neutre et vérifie que les aides natives Codex ne peuvent pas devenir des chemins opérationnels parallèles ; l’intégration ACP elle-même reste un lot de frontière ultérieur. Voir [README.md](README.md) pour la documentation anglaise.
