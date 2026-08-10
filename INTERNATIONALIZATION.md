# Internationalization convention

[Français](#français) | [English](#english)

## Français

Toute nouvelle App du dépôt doit être utilisable en français et en anglais dès
sa première version publique, sauf si elle expose exclusivement une interface
amont qui gère déjà nativement ses langues.

### Interface Home Assistant

- Ajouter `translations/fr.yaml` et `translations/en.yaml` lorsqu'une App
  expose des options ou des ports configurables.
- Les deux fichiers doivent contenir exactement les mêmes clés sous
  `configuration` et `network`.
- Les noms et descriptions doivent expliquer l'effet réel de chaque option,
  ses unités et les conséquences de sécurité importantes.
- `config.yaml` conserve des métadonnées courtes en anglais, utilisées comme
  valeur neutre lorsque Supervisor ne fournit pas de traduction.

### Interface web développée dans le dépôt

- Le français et l'anglais doivent couvrir tous les textes visibles : pages,
  formulaires, aides, placeholders, boutons, états, erreurs, confirmations,
  infobulles et attributs d'accessibilité.
- Au premier affichage, suivre la langue préférée du navigateur lorsqu'elle est
  `fr` ou `en`, puis utiliser le français comme langue de repli.
- Fournir un sélecteur manuel FR/EN visible et mémoriser son choix dans le
  navigateur. Le changement ne doit pas modifier les données de l'App.
- Traduire également les contenus générés dynamiquement. Ne pas limiter la
  traduction aux nœuds HTML présents au chargement.
- Adapter les dates, nombres et unités à la langue lorsque cela améliore la
  compréhension, sans traduire les identifiants techniques ni les données
  provenant des systèmes surveillés.
- Échapper les données avant insertion dans le HTML, quelle que soit la langue.

Les journaux techniques peuvent rester en anglais afin de conserver des termes
stables pour le diagnostic et la recherche. Une App enveloppant une interface
amont déjà multilingue ne doit pas créer une seconde couche de traduction.

### Documentation et validation

- Fournir `README.md` en anglais et `README.fr.md` en français.
- `DOCS.md`, affiché dans Home Assistant, doit permettre l'accès aux deux
  langues ou contenir les deux versions.
- Documenter la détection automatique, la langue de repli et le sélecteur
  manuel lorsqu'une interface web locale existe.
- Ajouter aux scripts de validation des contrôles de parité des traductions et
  des mécanismes de sélection de langue pertinents pour l'App.
- Tester au minimum le chargement initial en français et en anglais ainsi que
  les principaux textes dynamiques avant publication.
- Mentionner l'internationalisation dans le `CHANGELOG.md` et incrémenter la
  version de l'App.

## English

Every new App in this repository must be usable in French and English from its
first public release, unless it exclusively exposes an upstream interface that
already provides native language support.

### Home Assistant interface

- Add `translations/fr.yaml` and `translations/en.yaml` when an App exposes
  configurable options or ports.
- Both files must contain exactly the same keys under `configuration` and
  `network`.
- Names and descriptions must explain the actual effect of each option, its
  units, and important security consequences.
- Keep short English metadata in `config.yaml` as a neutral fallback when the
  Supervisor does not provide a translation.

### Repository-developed web interface

- French and English must cover every visible string: pages, forms, help text,
  placeholders, buttons, states, errors, confirmations, tooltips, and
  accessibility attributes.
- On first use, follow the browser's preferred language when it is `fr` or
  `en`, then fall back to French.
- Provide a visible manual FR/EN selector and remember its choice in the
  browser. Changing language must not modify App data.
- Translate dynamically generated content as well as the HTML present at page
  load.
- Localize dates, numbers, and units when useful, while keeping technical
  identifiers and monitored-system data unchanged.
- Escape data before inserting it into HTML in either language.

Technical logs may remain in English to preserve stable diagnostic and search
terms. An App wrapping an already multilingual upstream interface must not add
a second translation layer.

### Documentation and validation

- Provide an English `README.md` and a French `README.fr.md`.
- Home Assistant's `DOCS.md` must provide access to both languages or contain
  both versions.
- Document browser detection, fallback language, and the manual selector when
  a local web interface exists.
- Extend validation scripts with translation-key parity and relevant language
  selection checks for the App.
- Test at least the initial French and English rendering and the main dynamic
  messages before release.
- Record internationalization in `CHANGELOG.md` and increment the App version.
