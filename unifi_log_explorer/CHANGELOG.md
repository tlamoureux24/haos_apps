# Changelog

## 1.1.7

- Require either system certificate validation or a configured SHA-256 certificate fingerprint before sending the UniFi API key.
- Verify a pinned self-generated certificate on the established TLS socket before transmitting `X-API-KEY`, with explicit startup, probe and collection errors for missing or mismatched fingerprints.
- Redact the API key from reflected UniFi error content and document fingerprint acquisition and certificate rotation in French and English.

## 1.1.6

- Complete the full HAOS complain-mode audit by analyzing only the events recorded after the final 1.1.5 profile replacement.
- Allow the two exact legacy S6 source directories, Python's cgroup CPU-limit probe and SQLite's bounded `/var/tmp/etilqs_*` temporary files.
- Explicitly deny the unnecessary non-interactive Bash `/dev/tty` probe instead of granting terminal access.
- Restore full AppArmor enforcement with CI invariants for every permission derived from the final HAOS audit segment.

## 1.1.5

- Return the narrowed profile to temporary AppArmor complain mode for a complete HAOS audit instead of discovering transient permissions through iterative enforced releases.
- Allow the exact `bashio` launcher alias, canonical script and Bash interpreter required by this App's `with-contenv` shebang.
- Retain the exact `s6-linux-init-hpr` shutdown paths discovered by the first enforced attempt.

## 1.1.4

- Allow the exact transient `s6-linux-init-hpr` shutdown executable through both its stable package alias and its current versioned target.
- Add a CI invariant for this enforce-only lifecycle path, which is too short-lived to appear in the running-process inventory.

## 1.1.3

- Complete the bounded HAOS AppArmor acceptance covering startup, Ingress, healthcheck, synthetic Syslog and CEF ingestion, Traffic Flows probing and collection, restart and shutdown.
- Restore full AppArmor enforcement after the diagnostic run produced no missing-permission audit events or functional regressions.
- Make CI reject complain mode so the accepted least-privilege profile cannot silently return to diagnostic operation.

## 1.1.2

- Replace broad AppArmor capabilities, file, network and executable-tree permissions with the targeted application and S6 runtime rules observed from the current Home Assistant base image.
- Restrict persistent writes to the SQLite database, its journal files, the encrypted UniFi API key and the atomic key temporary files.
- Add CI guards against broad AppArmor rules plus a runtime executable inventory and synthetic Syslog/CEF smoke test.
- Temporarily ship the narrowed profile in AppArmor complain mode for one bounded HAOS acceptance pass before restoring enforcement in the next corrective release.

## 1.1.1

- Move the persistent language and light/dark controls from Settings into compact right-aligned header toggles matching UniFi Autoblock.
- Display the container `BUILD_VERSION` beside the UniFi Log Explorer name with a `dev` fallback outside Home Assistant builds.

## 1.1.0

- Move the existing administration interface to Home Assistant Ingress and stop publishing TCP port 8090 on the LAN.
- Remove local account setup, login, logout, password management, sessions, and login rate limiting; Home Assistant now authenticates administrators.
- Preserve every navigation, asset, filter, detail, export, form, theme, language, and redirect URL under the dynamic Ingress prefix.
- Keep state-changing actions protected by a constant-time checked, process-scoped CSRF token independent of authentication.
- Require the validated Supervisor Ingress proxy source and `X-Ingress-Path` context for UI routes while keeping `/health` available to the watchdog.
- Replace frame-blocking headers with a restrictive Ingress-compatible CSP and remove the standalone browser favicon route.
- Retain the deprecated `session_timeout_minutes` schema entry as optional, ignored upgrade compatibility for existing installations.

## 1.0.0

- Mark the application as stable after validation of collection, exploration, security, maintenance, and bilingual interfaces.
- Move the automated test suite into a dedicated `tests` directory.
- Keep development tests in the source repository while excluding them from the runtime Docker image.

## 0.9.0

- Add French and English web interfaces with browser-language detection.
- Add a persistent manual language selector before and after authentication.
- Keep French as the fallback language when no supported preference is available.
- Localize navigation, authentication, explorers, details, status, Settings, and maintenance controls.
- Accept the localized destructive-action confirmation in either supported language.

## 0.8.0

- Rate-limit repeated web login failures with a temporary per-client block.
- Add administrator password changes and invalidate every session afterwards.
- Add complete detail pages for archived CEF and Syslog events.
- Detect stale Traffic Flows collection cycles in Settings.
- Show SQLite size, stored volumes, and the next scheduled reconciliation.
- Add filtered CSV exports for Traffic Flows and CEF/Syslog events.
- Add a dependency-free 24-hour activity chart to the overview.
- Add explicit, CSRF-protected data maintenance controls with typed confirmation.

## 0.6.0

- Add a dedicated Settings page and replace the authenticated theme menu entry.
- Move appearance selection, API testing and diagnostic export into Settings.
- Add a read-only summary of the Home Assistant App configuration.
- Remove the diagnostic export action from the CEF / Syslog explorer.
- Keep the pre-login appearance switch available.
- Rewrite the French and English documentation for the completed explorer.

## 0.5.2

- Place the collection status in the right side of the overview heading, alongside the page title.
- Stack the heading and status cleanly on narrow screens.

## 0.5.1

- Move the collection status banner below the page header and above the overview metrics.

## 0.5.0

- Rename the Journaux section to CEF / Syslog to clarify its contents.
- Replace the fixed 100-event view with paginated access to retained events.
- Add full-text, event-type, source-address and time-period filters.
- Preserve filters while moving between result pages.
- Redirect the former `/logs` route to the new `/events` explorer.

## 0.4.3

- Fix inactive navigation links whose empty unquoted class consumed the `href` attribute.
- Keep long overview labels on one line with safe ellipsis truncation.
- Preserve full ranking labels in the hover tooltip.
- Validate navigation links by parsing the generated HTML structure.

## 0.4.2

- Rebuild the authenticated header with reliable, isolated navigation controls.
- Add the application icon next to the title on authenticated pages.
- Add All, CEF and Syslog journal filters.
- Link the overview CEF and Syslog metrics to their matching journal filters.
- Remove the unused flow-export receiver and its network port, code, tests and documentation.

## 0.4.1

- Redesign the login and initial setup pages around the application logo.
- Make the light/dark theme switch available before authentication.
- Serve the application icon as the browser favicon.
- Make overview metrics and rankings link to their corresponding filtered views.
- Prevent the hidden logout security field from covering navigation links.
- Harden flow rendering against heterogeneous endpoint data.

## 0.4.0

- Add a 24-hour analytical overview.
- Add the paginated explorer with search and filters.
- Add a detail view exposing every archived UniFi flow field.
- Separate Syslog/CEF events from network flow exploration.
- Add a light default theme with a persistent light/dark switch.
- Bound fast scans to five pages and reconcile late flows every six hours.

## 0.3.1

- Replace narrow cursor windows with newest-first scanning until known pages are reached.
- Add a one-time, chunked 24-hour repair to recover flows missed by delayed UniFi batches.
- Keep idle polling to two API pages while fully paging newly published batches.
- Parse multiline RFC3164 messages and timestamp-less UniFi switch messages.

## 0.3.0

- Add opt-in periodic collection of complete Traffic Flows through the local API.
- Poll every two minutes by default with a two-minute overlap.
- Paginate and split large time windows below UniFi's 10,000-result cap.
- Deduplicate flows by their stable UniFi identifier.
- Persist the collection cursor and resume after restarts with a 24-hour safety cap.
- Bound archived flows by the configured age and record limits.
- Show archived flow count and last collection-cycle status in the web UI.

## 0.2.0

- Add a manual, non-persistent probe for the internal Traffic Flows endpoint.
- Authenticate the probe with a dedicated UniFi API key.
- Encrypt the API key locally and clear it from Supervisor options after restart.
- Request at most one flow from the last five minutes and retain no returned flow.

## 0.1.1

- Parse the RFC3164 system logs that UniFi sends alongside CEF events.
- Display Syslog messages separately instead of reporting them as CEF errors.
- Count rejected datagrams by source address without retaining their payload.

## 0.1.0

- Add standalone authenticated web setup and administration interface.
- Receive UniFi Syslog/CEF over UDP.
- Reject traffic before parsing unless its exact source address is allowed.
- Parse CEF headers and extension fields.
- Bound diagnostic storage by age and record count.
- Export diagnostic data as JSON without the gateway sender address.
- Add original transparent icon and logo assets.
