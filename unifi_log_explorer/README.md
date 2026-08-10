# UniFi Log Explorer

UniFi Log Explorer is a standalone Home Assistant App that locally collects and
explores UniFi Traffic Flows together with Syslog/CEF exports.

See [README.fr.md](README.fr.md) for the complete current documentation.

The App has no Ingress. It publishes a local web interface with independent
authentication and a UDP listener for Syslog/CEF (`5514`). Only exact
addresses listed in `allowed_source_ips` are parsed or retained; the default is
`192.168.1.1`.

It includes a 24-hour analytical overview, a searchable and paginated flow
explorer, full flow details, a searchable and paginated CEF/Syslog explorer and persistent light/dark
themes. Traffic Flows are collected with a locally encrypted UniFi API key.
