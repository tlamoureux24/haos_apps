# CI policy / Politique CI

## Français

La CI sépare la documentation, la validation propre à chaque App et les tests
d’intégration transversaux. L’objectif est de conserver une validation forte
sans reconstruire des images pour une modification sans effet sur le runtime.

### Documentation

Toute modification Markdown déclenche uniquement **Validate Documentation**,
sauf si le même commit modifie aussi du code ou un workflow. Ce contrôle
vérifie l’UTF-8, les liens locaux et l’absence d’un numéro de version courante
dupliqué dans les documents utilisateur des Apps agents.

### Apps

Le workflow orchestrateur **Validate Agent Apps** détecte séparément les
modifications ACP, AEP et MCP Bridge, puis appelle uniquement les validations
complètes nécessaires. Une modification purement documentaire ne construit
aucune image. Les workflows propres aux Apps restent aussi exécutables
manuellement et servent de composants réutilisables à l’orchestrateur.

### Suite TLS agents

L’orchestrateur active la suite TLS uniquement pour les fichiers qui peuvent
modifier les listeners publics, les certificats, le pinning, les transports
MCP/HTTP ou les frontières sortantes ACP/AEP/Bridge. Chaque App produit alors
une image amd64 une seule fois. Ces trois images sont transférées comme
artefacts internes au job TLS, qui les charge et exécute la matrice sans les
reconstruire. Une App inchangée fournit seulement son image ; sa validation
complète n’est pas rejouée. La suite autonome reste exécutable manuellement.

### Caches

Les workflows ACP, AEP et MCP Bridge mettent en cache les téléchargements de
leurs dépendances Python à partir de leur propre `requirements.txt`. Une
dépendance modifiée est récupérée normalement ; le cache ne permet pas de
contourner un test.

### Concurrence

Les workflows de validation utilisent un groupe par workflow et référence avec
`cancel-in-progress: true`. Un nouveau push annule le run devenu obsolète de la
même branche. Les workflows automatiques de mise à jour gardent leur politique
distincte afin de ne pas interrompre un commit de mise à niveau en cours.

## English

CI separates documentation, per-App validation, and cross-App integration
tests. It retains strong validation without rebuilding images for changes that
cannot affect runtime behavior.

### Documentation

Any Markdown change triggers only **Validate Documentation**, unless the same
commit also changes code or a workflow. The check validates UTF-8, local links,
and the absence of duplicated current-version labels in agent App user docs.

### Apps

The **Validate Agent Apps** orchestrator detects ACP, AEP, and MCP Bridge
changes separately, then calls only the required full validations.
Documentation-only changes build no image. Per-App workflows also remain
manually dispatchable and act as reusable components for the orchestrator.

### Agent TLS suite

The orchestrator enables the TLS suite only for files that can affect public
listeners, certificates, pinning, MCP/HTTP transports, or ACP/AEP/Bridge
outbound boundaries. Each App then produces one amd64 image exactly once. The
three images are transferred as internal artifacts to the TLS job, which loads
them and runs the matrix without rebuilding. An unchanged App only supplies its
image; its full validation is not rerun. The standalone suite remains manually
dispatchable.

### Caches

The ACP, AEP, and MCP Bridge workflows cache Python dependency downloads based
on their respective `requirements.txt` files. A changed dependency is fetched
normally; caching cannot skip a test.

### Concurrency

Validation workflows use one group per workflow and ref with
`cancel-in-progress: true`. A newer push cancels an obsolete run for the same
branch. Automated update workflows retain their separate policy so an active
upgrade commit is not interrupted.
