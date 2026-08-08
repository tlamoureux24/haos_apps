import importlib.util
import struct
import unittest
from unittest import mock
from pathlib import Path

spec = importlib.util.spec_from_file_location("ule", Path(__file__).with_name("unifi_log_explorer.py"))
ule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ule)


class ParserTests(unittest.TestCase):
    def test_cef(self):
        event = ule.parse_syslog_or_cef(b"<134>CEF:0|Ubiquiti|UniFi Network|9.3.33|401|WiFi Client Disconnected|2|UNIFIclientIp=192.168.1.20 UNIFIclientAlias=Phone msg=Phone disconnected")
        self.assertEqual(event["event_id"], "401")
        self.assertEqual(event["fields"]["UNIFIclientIp"], "192.168.1.20")
        self.assertEqual(event["fields"]["msg"], "Phone disconnected")

    def test_unifi_rfc3164_syslog(self):
        event = ule.parse_syslog_or_cef(b"<30>Aug  8 09:19:57 UCG-Fiber UCG-Fiber dnsmasq-dhcp[3487]: DHCPACK(br0) 192.168.1.20 aa:bb:cc:dd:ee:ff phone")
        self.assertEqual(event["_kind"], "syslog")
        self.assertEqual(event["facility"], 3)
        self.assertEqual(event["severity"], 6)
        self.assertEqual(event["hostname"], "UCG-Fiber")
        self.assertEqual(event["app_name"], "dnsmasq-dhcp")
        self.assertEqual(event["process_id"], 3487)
        self.assertIn("DHCPACK", event["message"])

    def test_ipfix_template_and_data(self):
        fields = struct.pack("!HHHHHH", 8, 4, 12, 4, 1, 8)
        template = struct.pack("!HH", 256, 3) + fields
        template_set = struct.pack("!HH", 2, len(template) + 4) + template
        data = bytes([192,168,1,20, 1,1,1,1]) + (1234).to_bytes(8, "big")
        data_set = struct.pack("!HH", 256, len(data) + 4) + data
        length = 16 + len(template_set) + len(data_set)
        packet = struct.pack("!HHIII", 10, length, 1, 2, 3) + template_set + data_set
        parsed = ule.parse_ipfix(packet)
        tmpl = parsed["sets"][0]["templates"][0]
        samples, error = ule.decode_ipfix_records(parsed["sets"][1]["_payload"], tmpl)
        self.assertIsNone(error)
        self.assertEqual(samples[0]["sourceIPv4Address"], "192.168.1.20")
        self.assertEqual(samples[0]["octetDeltaCount"], 1234)

    def test_reject_netflow_v9(self):
        with self.assertRaisesRegex(ValueError, "unsupported flow version 9"):
            ule.parse_ipfix(struct.pack("!HHIII", 9, 16, 0, 0, 0))

    def test_flow_probe_uses_api_key_and_discards_flow(self):
        response = mock.MagicMock()
        response.read.return_value = b'{"data":[{"id":"sample","service":"HTTPS"}],"total_element_count":7,"has_next":true}'
        response.__enter__.return_value = response
        options = {"unifi_base_url": "https://192.168.1.1", "unifi_site_slug": "default",
                   "unifi_api_key": "secret-test-key", "verify_ssl": False}
        with mock.patch.object(ule.urllib.request, "urlopen", return_value=response) as urlopen:
            result = ule.flow_probe(options)
        request = urlopen.call_args.args[0]
        payload = ule.json.loads(request.data)
        self.assertEqual(request.full_url, "https://192.168.1.1/proxy/network/v2/api/site/default/traffic-flows")
        self.assertEqual(request.get_header("X-api-key"), "secret-test-key")
        self.assertEqual(payload["pageSize"], 1)
        self.assertEqual(result["total"], 7)
        self.assertNotIn("data", result)


if __name__ == "__main__":
    unittest.main()
