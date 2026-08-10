# Changelog

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
