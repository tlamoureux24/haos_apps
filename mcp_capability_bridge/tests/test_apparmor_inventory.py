from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_apparmor_inventory import covered, executable_rules, main


class AppArmorInventoryTests(unittest.TestCase):
    def test_chromium_proc_and_font_roots_are_explicitly_readable(self):
        profile = (Path(__file__).resolve().parents[1] / "apparmor.txt").read_text(encoding="utf-8")
        for rule in (
            "/proc/ r,",
            "/proc/** r,",
            "/etc/fonts/{,**} r,",
            "/var/cache/fontconfig/{,**} r,",
            "/usr/share/fonts/{,**} r,",
            "/usr/share/fontconfig/{,**} r,",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, profile)

    def test_exact_and_version_wildcard_rules_cover_observed_paths(self):
        rules = executable_rules("  /bin/sh ix,\n  /usr/bin/python3.* ix,\n  \"/path/with space\" rix,\n")
        self.assertTrue(covered("/bin/sh", rules))
        self.assertTrue(covered("/usr/bin/python3.13", rules))
        self.assertTrue(covered("/path/with space", rules))
        self.assertFalse(covered("/usr/bin/curl", rules))

    def test_validator_fails_closed_for_uncovered_runtime_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "profile").write_text("  /bin/sh ix,\n", encoding="utf-8")
            (root / "inventory").write_text("/bin/sh\n/usr/bin/python3\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "/usr/bin/python3"):
                with patch.object(sys, "argv", ["validator", str(root / "profile"), str(root / "inventory")]):
                    main()


if __name__ == "__main__":
    unittest.main()
