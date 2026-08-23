from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
try:
    import cryptography.fernet  # noqa: F401
except ModuleNotFoundError:
    cryptography = types.ModuleType("cryptography")
    fernet = types.ModuleType("cryptography.fernet")
    fernet.Fernet = mock.Mock
    fernet.InvalidToken = type("InvalidToken", (Exception,), {})
    cryptography.fernet = fernet
    sys.modules["cryptography"] = cryptography
    sys.modules["cryptography.fernet"] = fernet
SPEC = importlib.util.spec_from_file_location("unifi_autoblock", APP_DIR / "unifi_autoblock.py")
app = importlib.util.module_from_spec(SPEC)
sys.modules["unifi_autoblock"] = app
assert SPEC.loader
SPEC.loader.exec_module(app)


def traffic_list(values: list[str]) -> dict:
    return {
        "type": app.LIST_TYPE,
        "id": "list-id",
        "name": "IP BAN",
        "items": [{"type": app.ITEM_TYPE, "value": value} for value in values],
    }


def event(ip: str = "8.8.8.8") -> dict:
    return {
        "name": "Threat Detected and Blocked",
        "severity": 5,
        "alarm_id": "alarm-1",
        "parameters": {
            "act": "blocked",
            "UNIFIdirection": "incoming",
            "UNIFIpolicyType": "IDS/IPS",
            "src": ip,
            "dst": "192.168.1.15",
            "dpt": 443,
            "proto": "TCP",
            "UNIFIipsSignature": "Test signature",
            "UNIFIsrcRegion": "FR",
        },
    }


class Config:
    dry_run = False
    min_severity = 0
    allowed_destinations: set[str] = set()
    allowed_destination_ports = {443}
    allowlist_cidrs: list = []
    ban_ttl_days = 30
    traffic_matching_list_name = "IP BAN"
    traffic_matching_list_id = "list-id"
    unifi_site_id = "site-id"


class Client:
    def __init__(self, reads: list[dict], fail_update: bool = False):
        self.reads = iter(reads)
        self.fail_update = fail_update
        self.updates = []

    def get_traffic_list(self):
        return next(self.reads)

    def update_traffic_list(self, payload):
        if self.fail_update:
            raise RuntimeError("PUT failed")
        self.updates.append(payload)


class AutoblockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.paths = mock.patch.multiple(
            app,
            STATE_PATH=str(root / "state.json"),
            HISTORY_PATH=str(root / "history.json"),
            LAST_BACKUP_PATH=str(root / "backup.json"),
        )
        self.paths.start()
        self.addCleanup(self.paths.stop)
        self.events = mock.patch.object(app, "fire_homeassistant_event")
        self.events.start()
        self.addCleanup(self.events.stop)

    def history(self):
        return app.load_history()

    def test_pinned_tls_is_verified_before_api_key_is_sent(self):
        certificate = b"test-certificate"
        config = mock.Mock(
            verify_ssl=False,
            unifi_certificate_sha256=hashlib.sha256(certificate).hexdigest(),
            unifi_api_key="secret-test-key",
        )
        response = mock.MagicMock(status=200)
        response.read.return_value = b'{"data": []}'
        connection = mock.MagicMock()
        connection.sock.getpeercert.return_value = certificate
        connection.getresponse.return_value = response
        with mock.patch.object(app.http.client, "HTTPSConnection", return_value=connection):
            result = app.UniFiClient(config).request("GET", "https://192.168.1.1/test")
        self.assertEqual(result, {"data": []})
        connection.connect.assert_called_once_with()
        connection.request.assert_called_once()
        self.assertEqual(connection.request.call_args.kwargs["headers"]["X-API-KEY"], "secret-test-key")

    def test_pinned_tls_mismatch_refuses_before_api_key_is_sent(self):
        config = mock.Mock(
            verify_ssl=False,
            unifi_certificate_sha256="0" * 64,
            unifi_api_key="secret-test-key",
        )
        connection = mock.MagicMock()
        connection.sock.getpeercert.return_value = b"different-certificate"
        with mock.patch.object(app.http.client, "HTTPSConnection", return_value=connection):
            with self.assertRaisesRegex(RuntimeError, "fingerprint mismatch"):
                app.UniFiClient(config).request("GET", "https://192.168.1.1/test")
        connection.request.assert_not_called()

    def test_blocked_is_recorded_only_after_verified_update(self):
        client = Client([traffic_list([]), traffic_list(["8.8.8.8"])])
        self.assertEqual("blocked", app.process_event(event(), Config(), client)["status"])
        self.assertEqual(["blocked"], [entry["action"] for entry in self.history()])
        self.assertEqual("Test signature", self.history()[0]["signature"])

    def test_failed_update_does_not_record_blocked(self):
        client = Client([traffic_list([])], fail_update=True)
        with self.assertRaisesRegex(RuntimeError, "PUT failed"):
            app.process_event(event(), Config(), client)
        self.assertEqual([], self.history())

    def test_failed_verification_does_not_record_blocked(self):
        client = Client([traffic_list([]), traffic_list([])])
        with self.assertRaisesRegex(RuntimeError, "verification failed"):
            app.process_event(event(), Config(), client)
        self.assertEqual([], self.history())

    def test_already_present_is_recorded(self):
        client = Client([traffic_list(["8.8.8.8"])])
        self.assertEqual("already_present", app.process_event(event(), Config(), client)["status"])
        self.assertEqual("already_present", self.history()[0]["action"])

    def test_expired_is_recorded_only_after_successful_removal(self):
        expired = "9.9.9.9"
        app.save_json_file(app.STATE_PATH, {"version": 1, "managed_ips": {expired: {"expires_at": "2000-01-01T00:00:00+00:00"}}})
        failing = Client([traffic_list([expired, "8.8.8.8"])], fail_update=True)
        with self.assertRaisesRegex(RuntimeError, "PUT failed"):
            app.process_event(event(), Config(), failing)
        self.assertEqual([], self.history())

        app.save_json_file(app.STATE_PATH, {"version": 1, "managed_ips": {expired: {"expires_at": "2000-01-01T00:00:00+00:00"}}})
        success = Client([traffic_list([expired, "8.8.8.8"])])
        app.process_event(event(), Config(), success)
        self.assertEqual(["expired", "already_present"], [entry["action"] for entry in self.history()])

    def test_history_is_persistent_and_bounded(self):
        for index in range(1002):
            app.append_history("expired", f"198.51.100.{index}")
        persisted = app.load_history()
        self.assertEqual(1000, len(persisted))
        self.assertEqual("198.51.100.2", persisted[0]["ip"])
        self.assertEqual("198.51.100.1001", persisted[-1]["ip"])
        self.assertEqual(1000, len(json.loads(Path(app.HISTORY_PATH).read_text())))

    def test_ingress_history_and_prefixed_assets(self):
        ingress_ui = __import__("ingress_ui")
        app.append_history("blocked", "8.8.8.8", {"severity": 5})

        def request(path, headers=None):
            handler = ingress_ui.IngressHandler.__new__(ingress_ui.IngressHandler)
            handler.path = path
            handler.headers = headers or {}
            handler.server = type("Server", (), {"history_loader": staticmethod(app.load_history)})()
            captured = {}
            handler.send_body = lambda status, body, content_type: captured.update(
                status=status, body=body, content_type=content_type
            )
            handler.do_GET()
            return captured

        page_response = request("/", {"X-Ingress-Path": "/api/hassio_ingress/token"})
        self.assertEqual(200, page_response["status"])
        page = page_response["body"].decode()
        self.assertIn('/api/hassio_ingress/token/assets/app.css', page)
        history_response = request("/api/history")
        self.assertEqual(200, history_response["status"])
        self.assertEqual("8.8.8.8", json.loads(history_response["body"])["history"][0]["ip"])
        for path in ("/assets/app.css", "/assets/app.js", "/assets/icon.png"):
            self.assertEqual(200, request(path)["status"])

    def test_existing_health_surface_is_unchanged(self):
        handler = app.Handler.__new__(app.Handler)
        handler.path = "/health"
        handler.server = type("Server", (), {"config": Config()})()
        with mock.patch.object(handler, "send_json") as send_json:
            handler.do_GET()
        send_json.assert_called_once_with(200, {"status": "ok", "dry_run": False})

    def test_existing_webhook_surface_still_processes_events(self):
        handler = app.Handler.__new__(app.Handler)
        payload = json.dumps(event()).encode()
        handler.path = "/webhook/token"
        handler.headers = {"Content-Length": str(len(payload)), "Authorization": "Bearer auth"}
        handler.client_address = ("127.0.0.1", 12345)
        handler.rfile = io.BytesIO(payload)
        config = Config()
        config.webhook_token = "token"
        config.webhook_auth_token = "auth"
        handler.server = type("Server", (), {"config": config, "unifi_client": object()})()
        with (
            mock.patch.object(app, "is_allowed_source", return_value=True),
            mock.patch.object(app, "process_event", return_value={"status": "blocked"}) as process,
            mock.patch.object(handler, "send_json") as send_json,
        ):
            handler.do_POST()
        process.assert_called_once()
        send_json.assert_called_once_with(200, {"status": "blocked"})


if __name__ == "__main__":
    unittest.main()
