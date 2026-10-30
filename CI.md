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

### Images des Apps

Chaque `config.yaml` déclare `image: "ghcr.io/tlamoureux24/{arch}-<slug>"`.
Le Supervisor télécharge donc une image précompilée au lieu de construire l’App
sur la machine Home Assistant, qui n’accumule plus de cache de compilation
Docker à chaque installation ou mise à jour.

Le workflow **Publish App Images** construit chaque architecture déclarée sur
un runner natif (`amd64` sur `ubuntu-24.04`, `aarch64` sur `ubuntu-24.04-arm`)
avec les mêmes `BUILD_ARCH` et `BUILD_VERSION` que les validations, puis pousse
le tag égal à `version`. L’image porte l’empreinte de son contexte de
construction, Markdown exclu. Un tag déjà publié avec la même empreinte n’est
pas reconstruit. Un tag déjà publié pour la version présente sur `main` n’est
jamais remplacé : modifier le runtime exige une nouvelle version. Chaque run
vérifie enfin que l’image se télécharge sans authentification, comme le fait
le Supervisor.

Ordre de publication :

- les workflows de mise à jour automatique valident puis poussent leur commit
  sur une branche `automation/<app>-update`. Les images de ce commit sont
  publiées, puis `main` avance par fast-forward, ou par rebase si le contexte
  des Apps publiées reste identique. Le Supervisor ne voit donc jamais une
  version dont l’image manque ;
- une version modifiée et poussée directement sur `main` déclenche aussi la
  publication, mais reste visible sans image pendant la construction. Pour
  éviter cette fenêtre, pousser d’abord une branche, puis lancer
  `gh workflow run app-images-publish.yml --ref <branche> -f apps=<slug> -f promote=true` :
  le workflow publie les images, puis fait avancer `main` ;
- un tag publié depuis une branche puis modifié avant d’atteindre `main` est
  reconstruit, puisqu’aucune installation n’a pu l’utiliser.

Chaque paquet GHCR doit être public. Si GitHub crée un nouveau paquet en
privé, le passer en public une fois dans ses paramètres ; tant que ce n’est
pas fait, la vérification anonyme échoue et la nouvelle version n’atteint pas
`main`.

### Caches

Les workflows ACP, AEP et MCP Bridge mettent en cache les téléchargements de
leurs dépendances Python à partir de leur propre `requirements.txt`. Une
dépendance modifiée est récupérée normalement ; le cache ne permet pas de
contourner un test.

### Concurrence

Les workflows de validation utilisent un groupe par workflow et référence avec
`cancel-in-progress: true`. Un nouveau push annule le run devenu obsolète de la
même branche. Les workflows automatiques de mise à jour gardent leur politique
distincte afin de ne pas interrompre un commit de mise à niveau en cours. La
publication d’une image est sérialisée par App et architecture, et
l’avancement de `main` par un groupe unique, sans annulation.

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

### App images

Every `config.yaml` declares `image: "ghcr.io/tlamoureux24/{arch}-<slug>"`.
Supervisor therefore downloads a prebuilt image instead of building the App on
the Home Assistant machine, which no longer accumulates Docker build cache on
every installation or update.

The **Publish App Images** workflow builds each declared architecture on a
native runner (`amd64` on `ubuntu-24.04`, `aarch64` on `ubuntu-24.04-arm`) with
the same `BUILD_ARCH` and `BUILD_VERSION` as the validations, then pushes the
tag matching `version`. The image records a digest of its build context,
excluding Markdown. A tag already published with the same digest is not
rebuilt. A tag already published for the version on `main` is never replaced:
changing the runtime requires a new version. Each run finally checks that the
image can be pulled without authentication, as Supervisor does.

Publication order:

- automated update workflows validate, then push their commit to an
  `automation/<app>-update` branch. The images for that commit are published,
  then `main` moves by fast-forward, or by rebase when the published Apps keep
  an identical build context. Supervisor therefore never sees a version whose
  image is missing;
- a version changed and pushed directly to `main` also triggers publication,
  but is visible without an image while it builds. To avoid that window, push
  a branch first, then run
  `gh workflow run app-images-publish.yml --ref <branch> -f apps=<slug> -f promote=true`:
  the workflow publishes the images, then moves `main`;
- a tag published from a branch and changed before reaching `main` is rebuilt,
  since no installation could have used it.

Every GHCR package must be public. If GitHub creates a new package as private,
make it public once in its settings; until then, the anonymous check fails and
the new version does not reach `main`.

### Caches

The ACP, AEP, and MCP Bridge workflows cache Python dependency downloads based
on their respective `requirements.txt` files. A changed dependency is fetched
normally; caching cannot skip a test.

### Concurrency

Validation workflows use one group per workflow and ref with
`cancel-in-progress: true`. A newer push cancels an obsolete run for the same
branch. Automated update workflows retain their separate policy so an active
upgrade commit is not interrupted. Image publication is serialized per App and
architecture, and moving `main` uses a single group, without cancellation.
