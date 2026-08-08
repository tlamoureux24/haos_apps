# UniFi Log Explorer

UniFi Log Explorer is a standalone Home Assistant App that receives and inspects
IPFIX and Syslog/CEF exports from a UniFi gateway. Version `0.1.0` is the
diagnostic collection phase used to discover the gateway's real exported fields
before the analytical storage schema and final UI are designed.

See [README.fr.md](README.fr.md) for the complete current documentation.

The App has no Ingress. It publishes a local web interface with independent
authentication and UDP listeners for IPFIX (`2055`) and CEF (`5514`). Only exact
addresses listed in `allowed_source_ips` are parsed or retained; the default is
`192.168.1.1`.

Version `0.2.0` also includes a non-persistent diagnostic probe for the internal
Traffic Flows endpoint using a locally encrypted dedicated UniFi API key.
