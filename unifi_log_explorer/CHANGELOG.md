# Changelog

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
