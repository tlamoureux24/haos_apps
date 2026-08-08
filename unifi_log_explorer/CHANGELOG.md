# Changelog

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
