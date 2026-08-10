# Changelog

## 0.4.0

- Ajoute une vue d'ensemble analytique sur les dernières 24 heures.
- Ajoute l'explorateur paginé avec recherche et filtres.
- Ajoute une fiche détaillée donnant accès à tous les champs UniFi d'un flow.
- Sépare les journaux Syslog/CEF de l'exploration réseau.
- Ajoute un thème clair par défaut et une bascule persistante clair/sombre.
- Borne les scans rapides à cinq pages et réconcilie les flows tardifs toutes les six heures.

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
- Receive IPFIX v10 and UniFi Syslog/CEF over separate UDP ports.
- Reject traffic before parsing unless its exact source address is allowed.
- Default the allowed source list to `192.168.1.1`.
- Inventory IPFIX templates and decode fixed-length record samples.
- Parse CEF headers and extension fields.
- Bound diagnostic storage by age and record count.
- Export diagnostic data as JSON without the gateway sender address.
- Add original transparent icon and logo assets.
