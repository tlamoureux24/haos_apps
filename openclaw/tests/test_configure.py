from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "configure.py"
SPEC = importlib.util.spec_from_file_location("openclaw_configure", MODULE_PATH)
assert SPEC and SPEC.loader
configure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(configure)


class ConfigureTests(unittest.TestCase):
    def test_applies_gateway_and_mcp_without_destroying_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            options = root / "options.json"
            config = root / "openclaw.json"
            options.write_text(json.dumps({
                "allowed_origins": "http://ha.local:18789, https://claw.example.test",
                "ha_mcp_url": "http://ha.local:9583/private_abcDEF123_-",
            }), encoding="utf-8")
            config.write_text(json.dumps({"custom": {"keep": True}}), encoding="utf-8")

            configure.apply(options, config, "/config/workspace")
            result = json.loads(config.read_text(encoding="utf-8"))

            self.assertEqual(result["custom"], {"keep": True})
            self.assertEqual(result["gateway"]["auth"], {"mode": "token"})
            self.assertFalse(result["gateway"]["controlUi"]["dangerouslyDisableDeviceAuth"])
            self.assertEqual(
                result["mcp"]["servers"]["home-assistant"]["transport"],
                "streamable-http",
            )
            self.assertFalse(result["models"]["pricing"]["enabled"])

    def test_empty_mcp_url_removes_only_managed_server(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            options = root / "options.json"
            config = root / "openclaw.json"
            options.write_text(json.dumps({
                "allowed_origins": "http://homeassistant.local:18789",
                "ha_mcp_url": "",
            }), encoding="utf-8")
            config.write_text(json.dumps({"mcp": {"servers": {
                "home-assistant": {"url": "old"},
                "docs": {"url": "https://docs.example.test/mcp"},
            }}}), encoding="utf-8")

            configure.apply(options, config, "/config/workspace")
            servers = json.loads(config.read_text(encoding="utf-8"))["mcp"]["servers"]
            self.assertNotIn("home-assistant", servers)
            self.assertIn("docs", servers)

    def test_rejects_non_private_ha_mcp_url(self) -> None:
        with self.assertRaises(RuntimeError):
            configure.validate_mcp_url("http://ha.local:9583/mcp")


if __name__ == "__main__":
    unittest.main()
