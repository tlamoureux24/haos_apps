import os
import tempfile
import unittest
from pathlib import Path

from mcp_capability_bridge.tls import generate_certificate, prepare_certificate, stage_external_certificate


class TLSIdentityTests(unittest.TestCase):
    def test_self_generated_identity_is_persistent_and_regenerable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            first=prepare_certificate(root,"self_generated")
            same=prepare_certificate(root,"self_generated")
            self.assertEqual(first.fingerprint_sha256,same.fingerprint_sha256)
            self.assertEqual((root/"private/tls/server-key.pem").stat().st_mode&0o777,0o600)
            generate_certificate(root/"private/tls",replace=True)
            self.assertNotEqual(first.fingerprint_sha256,prepare_certificate(root,"self_generated").fingerprint_sha256)

    def test_external_paths_cannot_escape_ssl_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError,"external_certificate_path_invalid"):
                prepare_certificate(Path(temporary),"external","../cert.pem","key.pem",Path(temporary)/"ssl")

    def test_external_key_is_staged_privately_for_unprivileged_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/"ssl";source.mkdir();generate_certificate(source)
            certfile,keyfile=stage_external_certificate("server-cert.pem","server-key.pem",root/"private/external-tls",os.getuid(),os.getgid(),source)
            self.assertEqual(keyfile.stat().st_mode&0o777,0o600);self.assertEqual(certfile.stat().st_mode&0o777,0o644)
            self.assertEqual(prepare_certificate(root,"external",certfile.name,keyfile.name,certfile.parent).source,"external")


if __name__ == "__main__": unittest.main()
