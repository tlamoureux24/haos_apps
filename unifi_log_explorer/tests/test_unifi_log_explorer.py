import importlib.util
import tempfile
import unittest
from html.parser import HTMLParser
from unittest import mock
from pathlib import Path

spec = importlib.util.spec_from_file_location("ule", Path(__file__).resolve().parents[1] / "unifi_log_explorer.py")
ule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ule)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == "a": self.links.append(dict(attrs).get("href"))


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

    def test_multiline_and_switch_syslog_variants(self):
        multiline = ule.parse_syslog_or_cef(b"<14>Aug  9 02:01:46 UCG-Fiber UCG-Fiber linkcheck[953]: speedtest\nsecond line")
        self.assertEqual(multiline["app_name"], "linkcheck")
        self.assertIn("second line", multiline["message"])
        switch = ule.parse_syslog_or_cef(b"<30>USWUltra210W 6c63f82a3348,USW-Ultra-210W-2.1.8.971: switch: port changed")
        self.assertEqual(switch["hostname"], "USWUltra210W")
        self.assertIsNone(switch["timestamp"])
        self.assertIn("switch", switch["message"])

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

    def test_flow_storage_deduplicates_unifi_id(self):
        flow = {"id": "stable-id", "flow_start_time": 1000, "flow_end_time": 2000,
                "source": {"ip": "192.168.1.20"}, "destination": {"ip": "1.1.1.1"},
                "service": "HTTPS", "action": "allowed"}
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(ule, "DATA", Path(directory)), mock.patch.object(ule, "DB_PATH", Path(directory) / "test.db"):
                store = ule.Store({"retention_hours": 168, "max_records": 1000,
                                   "allowed_source_ips": {"192.168.1.1"}})
                self.assertEqual(store.add_flows([flow]), 1)
                self.assertEqual(store.add_flows([flow]), 0)
                self.assertEqual(store.dashboard()["flow_stats"]["count"], 1)

    def test_flow_explorer_filters_and_details(self):
        now = int(ule.time.time() * 1000)
        flow = {"id": "flow-searchable", "flow_start_time": now - 2000, "flow_end_time": now,
                "source": {"ip": "192.168.1.20", "name": "Téléphone"},
                "destination": {"ip": "9.9.9.9", "domains": ["dns.quad9.net"]},
                "direction": "outgoing", "service": "HTTPS", "action": "allowed"}
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(ule, "DATA", Path(directory)), mock.patch.object(ule, "DB_PATH", Path(directory) / "test.db"):
                store = ule.Store({"retention_hours": 168, "max_records": 1000,
                                   "allowed_source_ips": {"192.168.1.1"}})
                store.add_flows([flow])
                result = store.query_flows({"q": "quad9", "direction": "outgoing", "hours": 24})
                self.assertEqual(result["total"], 1)
                self.assertEqual(result["rows"][0]["id"], "flow-searchable")
                self.assertEqual(store.flow_by_id("flow-searchable")["detail"]["service"], "HTTPS")
                self.assertEqual(store.flow_overview()["services"][0], {"label": "HTTPS", "count": 1})

    def test_newest_scan_stops_after_two_known_pages(self):
        class FakeStore:
            options = {}
            known = {"known-1", "known-2"}
            def known_flow_ids(self, identifiers): return set(identifiers) & self.known
            def add_flows(self, flows):
                new = [flow["id"] for flow in flows if flow["id"] not in self.known]
                self.known.update(new)
                return len(new)
        pages = {
            1: {"data": [{"id": "new-1"}], "has_next": True},
            2: {"data": [{"id": "known-1"}], "has_next": True},
            3: {"data": [{"id": "known-2"}], "has_next": True},
            4: {"data": [{"id": "must-not-be-read"}], "has_next": False},
        }
        with mock.patch.object(ule, "traffic_flow_page", side_effect=lambda options, start, end, page, size: pages[page]) as request:
            totals = ule.FlowCollector(FakeStore()).scan_newest(2_000_000_000_000)
        self.assertEqual(totals, [3, 1, 3])
        self.assertEqual(request.call_count, 3)

    def test_newest_scan_is_bounded_when_pages_keep_changing(self):
        class FakeStore:
            options = {}
            def known_flow_ids(self, identifiers): return set()
            def add_flows(self, flows): return len(flows)
        page = {"data": [{"id": "new"}], "has_next": True}
        with mock.patch.object(ule, "traffic_flow_page", return_value=page) as request:
            totals = ule.FlowCollector(FakeStore()).scan_newest(2_000_000_000_000)
        self.assertEqual(totals, [5, 5, 5])
        self.assertEqual(request.call_count, 5)

    def test_reconciliation_schedule_is_initialized_without_immediate_repair(self):
        class FakeStore:
            values = {}
            def setting(self, key): return self.values.get(key)
            def set_setting(self, key, value): self.values[key] = value
        store = FakeStore()
        collector = ule.FlowCollector(store)
        self.assertFalse(collector.reconciliation_due(1_000_000))
        self.assertFalse(collector.reconciliation_due(1_000_001))
        self.assertTrue(collector.reconciliation_due(1_000_000 + collector.RECONCILE_INTERVAL_SECONDS))

    def test_ingress_navigation_routes_render_with_prefix(self):
        now = int(ule.time.time() * 1000)
        flow = {"id": "render-me", "flow_start_time": now - 1000, "flow_end_time": now,
                "source": {"ip": "192.168.1.20", "name": "Phone"},
                "destination": {"ip": "9.9.9.9"}, "direction": "outgoing",
                "service": "HTTPS", "action": "allowed"}
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(ule, "DATA", Path(directory)), mock.patch.object(ule, "DB_PATH", Path(directory) / "test.db"):
                store = ule.Store({"retention_hours": 168, "max_records": 1000,
                                   "allowed_source_ips": {"192.168.1.1"}})
                store.add_flows([flow])
                store.add("cef", "192.168.1.1", "CEF only", {"name": "CEF only"})
                store.add("syslog", "192.168.1.1", "Syslog only", {"message": "Syslog only"})
                for number in range(10):
                    store.add("syslog", "192.168.1.20", f"Routine {number}", {"message": f"Routine {number}"})
                cef_id = store.query_events({"kind": "cef", "hours": 24})["rows"][0]["id"]
                for path in ("/", "/flows", "/events?size=10", "/events?kind=cef", f"/event?id={cef_id}", "/settings", "/flow?id=render-me"):
                    handler = ule.Web.__new__(ule.Web); handler.path = path
                    handler.headers = {"X-Ingress-Path": "/api/hassio_ingress/test-token"}
                    handler.client_address = (ule.INGRESS_PROXY_IP, 12345); handler.store = store
                    rendered = []
                    handler.send_html = lambda body, **kwargs: rendered.append(handler.prefix_markup(body))
                    handler.send_error = lambda code: self.fail(f"{path} returned HTTP {code}")
                    handler.do_GET()
                    self.assertTrue(rendered, path)
                    self.assertIn("Traffic Flows", rendered[0])
                    parser = LinkParser(); parser.feed(rendered[0])
                    prefix = "/api/hassio_ingress/test-token"
                    self.assertIn(prefix + "/", parser.links)
                    self.assertIn(prefix + "/flows", parser.links)
                    self.assertIn(prefix + "/events", parser.links)
                    self.assertIn(prefix + "/settings", parser.links)
                    self.assertFalse(any(link and link.startswith("/") and not link.startswith(prefix + "/") for link in parser.links))
                    if path == "/":
                        self.assertIn("class=overviewhead", rendered[0])
                        self.assertIn("class='card statuscard'", rendered[0])
                        self.assertIn("Activité horaire", rendered[0])
                        self.assertLess(rendered[0].index("Collecte en attente"), rendered[0].index("class=grid"))
                    if path == "/events?size=10":
                        self.assertTrue(any(link and link.startswith(prefix + "/events?") and "page=2" in link for link in parser.links))
                    if path == "/events?kind=cef":
                        self.assertIn("CEF only", rendered[0])
                        self.assertNotIn("Syslog only", rendered[0])
                        self.assertNotIn("Exporter le diagnostic JSON", rendered[0])
                    if path == "/settings":
                        self.assertIn("Exporter le diagnostic JSON", rendered[0])
                        self.assertIn("Lecture seule", rendered[0])
                        self.assertIn("Tester la connexion", rendered[0])
                        self.assertNotIn("Sécurité du compte", rendered[0])
                        self.assertIn(f"action={prefix}/probe", rendered[0])
                        self.assertIn(f"action={prefix}/purge", rendered[0])
                        self.assertIn(f"href={prefix}/export.json", rendered[0])
                        self.assertIn("Prochaine réconciliation", rendered[0])
                        self.assertIn("Maintenance des données", rendered[0])
                    if path.startswith("/event?"):
                        self.assertIn("CEF only", rendered[0])
                        self.assertIn("Données complètes", rendered[0])

                result = store.query_events({"kind": "syslog", "q": "Syslog only", "hours": 24}, page=1, page_size=10)
                self.assertEqual(result["total"], 1)
                self.assertEqual(result["rows"][0]["kind"], "syslog")
                self.assertGreaterEqual(len(store.timeline()), 24)
                self.assertEqual(len(store.export_flow_rows({"hours": 24})), 1)
                self.assertGreaterEqual(len(store.export_event_rows({"hours": 24})), 12)
                self.assertEqual(store.purge("flows"), 1)
                self.assertEqual(store.dashboard()["flow_stats"]["count"], 0)

    def test_ingress_context_and_health_exception(self):
        handler = ule.Web.__new__(ule.Web); handler.path = "/"; handler.headers = {}
        handler.client_address = ("192.168.1.20", 12345); handler.store = mock.MagicMock()
        denied = []
        handler.send_error = lambda code: denied.append(code)
        handler.do_GET()
        self.assertEqual(denied, [403])

        handler = ule.Web.__new__(ule.Web); handler.path = "/health"; handler.headers = {}
        handler.send_response = mock.Mock(); handler.send_header = mock.Mock(); handler.end_headers = mock.Mock()
        handler.wfile = mock.Mock()
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        handler.wfile.write.assert_called_once_with(b"OK")

    def test_ingress_security_headers_are_iframe_compatible(self):
        handler = ule.Web.__new__(ule.Web); handler.path = "/"; handler.headers = {"X-Ingress-Path": "/api/hassio_ingress/test-token"}
        sent = {}
        handler.send_response = lambda status: sent.update(status=status)
        handler.send_header = lambda key, value: sent.update({key: value})
        handler.end_headers = lambda: None; handler.wfile = mock.Mock()
        handler.send_html("<a href=/flows>Flows</a><img src=/icon.png><form action=/purge></form>")
        self.assertEqual(sent["status"], 200)
        self.assertNotIn("X-Frame-Options", sent)
        self.assertIn("frame-ancestors 'self'", sent["Content-Security-Policy"])
        self.assertNotIn("frame-ancestors 'none'", sent["Content-Security-Policy"])
        document = handler.wfile.write.call_args.args[0].decode()
        for target in ("/flows", "/icon.png", "/purge"):
            self.assertIn("/api/hassio_ingress/test-token" + target, document)

    def test_probe_and_purge_require_valid_csrf(self):
        def post(path, form):
            handler = ule.Web.__new__(ule.Web); handler.path = path
            handler.headers = {"X-Ingress-Path": "/api/hassio_ingress/test-token"}
            handler.client_address = (ule.INGRESS_PROXY_IP, 12345); handler.store = mock.MagicMock()
            handler.store.options = {"unifi_api_key": "key"}; handler.store.purge.return_value = 3
            handler.form = lambda: form
            errors = []; redirects = []
            handler.send_error = lambda code: errors.append(code)
            handler.redirect = lambda target, cookie=None: redirects.append(target)
            handler.do_POST()
            return handler, errors, redirects

        for path in ("/probe", "/purge"):
            _, errors, redirects = post(path, {})
            self.assertEqual(errors, [403]); self.assertFalse(redirects)
            _, errors, redirects = post(path, {"csrf": "invalid"})
            self.assertEqual(errors, [403]); self.assertFalse(redirects)
        with mock.patch.object(ule, "flow_probe", return_value={"ok": True}):
            handler, errors, redirects = post("/probe", {"csrf": ule.CSRF_TOKEN})
        self.assertFalse(errors); self.assertEqual(redirects, ["/settings"])
        handler.store.set_setting.assert_called_once()
        handler, errors, redirects = post("/purge", {"csrf": ule.CSRF_TOKEN, "confirm": "PURGER", "target": "events"})
        self.assertFalse(errors); self.assertEqual(redirects, ["/settings"])
        handler.store.purge.assert_called_once_with("events")

    def test_english_interface_and_language_override(self):
        handler = ule.Web.__new__(ule.Web); handler.path = "/settings"
        handler.headers = {"Accept-Language": "en-US,en;q=0.9"}
        self.assertEqual(handler.language(), "en")
        self.assertEqual(handler.t("Vue d’ensemble"), "Overview")
        nav = handler.nav("settings")
        self.assertIn("Overview", nav); self.assertIn("Settings", nav); self.assertNotIn("Sign out", nav)
        handler.headers = {"Accept-Language": "en", "Cookie": "ule_language=fr"}
        self.assertEqual(handler.language(), "fr")

    def test_local_authentication_is_removed(self):
        source = (Path(__file__).resolve().parents[1] / "unifi_log_explorer.py").read_text()
        for obsolete in ("ule_session", "SESSIONS", "LOGIN_ATTEMPTS", "password_hash", 'path == "/login"', 'path == "/setup"', 'path == "/logout"', 'path == "/password"'):
            self.assertNotIn(obsolete, source)
        self.assertEqual(ule.csv_safe("=SUM(A1:A2)"), "'=SUM(A1:A2)")


if __name__ == "__main__":
    unittest.main()
