# Changelog

## Unreleased

- Clarify the normative ACP/AEP responsibility boundary: ACP remains the sole authority for connector governance and operational capability selection; AEP consumes the source-supplied model capability envelope, performs only technical consistency checks, and keeps ACP lifecycle tools outside model visibility.

## 0.3.1

- Polish the bilingual Models table empty state, provider heading and provider-family labels.

## 0.3.0

- Add the official OpenAI ChatGPT OAuth provider family through the exactly pinned Codex 0.144.4 app-server over local stdio JSONL.
- Add shared device-code login, account/logout state and Codex model catalogue administration without exposing OAuth tokens or API-key fallback.
- Isolate Codex credentials under `/data/private/codex-home` and keep OAuth validation/health strictly non-inferential.

## 0.2.0

- Add encrypted configured-model persistence, deterministic ordering, enable/disable and positive per-model timeouts.
- Add Ollama-compatible metadata validation and OpenAI-compatible explicit tool-call validation.
- Add non-inference startup health and the bilingual responsive Models administration view.

## 0.1.2

- Align the Ingress administration container maximum width with Agent Control Plane at 1840 px.

## 0.1.1

- Align the generic s6-overlay AppArmor bootstrap rules with the HAOS-proven Agent Control Plane profile, including explicit directory traversal permissions.
- Clarify that the Docker executable inventory is evidence only and does not enforce or validate the HAOS AppArmor profile.

## 0.1.0

- Add the executable HAOS Lot 0 shell with isolated Ingress and standalone listeners.
- Add bilingual responsive light/dark administration views for Overview and Activity.
- Add generation-1 SQLite infrastructure and bounded persistent safe activity metadata.
- Add timestamped logging, unprivileged startup, AppArmor baseline, validation, tests, and CI.
