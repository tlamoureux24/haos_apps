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

Chaque workflow d’App surveille son arborescence en excluant les fichiers
Markdown. Un changement de code, configuration, traduction, packaging, test ou
asset conserve donc la validation complète de l’App. Une modification purement
documentaire ne construit aucune image. La modification du fichier YAML d’un
workflow déclenche volontairement ce workflow afin de valider son évolution.

### Suite TLS agents

La suite TLS surveille uniquement les fichiers qui peuvent modifier les
listeners publics, les certificats, le pinning, les transports MCP/HTTP ou les
frontières sortantes ACP/AEP/Bridge. Elle reste exécutable manuellement depuis
GitHub Actions.

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

Each App workflow watches its App tree while excluding Markdown. Code,
configuration, translation, packaging, test, and asset changes therefore retain
the complete App validation. Documentation-only changes build no image.
Changing a workflow YAML deliberately triggers that workflow so its evolution
is validated.

### Agent TLS suite

The TLS suite watches only files that can affect public listeners,
certificates, pinning, MCP/HTTP transports, or ACP/AEP/Bridge outbound
boundaries. It also remains manually dispatchable from GitHub Actions.

### Concurrency

Validation workflows use one group per workflow and ref with
`cancel-in-progress: true`. A newer push cancels an obsolete run for the same
branch. Automated update workflows retain their separate policy so an active
upgrade commit is not interrupted.
