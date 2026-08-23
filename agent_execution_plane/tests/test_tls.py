import tempfile
import unittest
from pathlib import Path

from agent_execution_plane.tls import generate_certificate, prepare_certificate


class TLSIdentityTests(unittest.TestCase):
    def test_self_generated_identity_is_persistent_and_regenerable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            first=prepare_certificate(root,"self_generated")
            same=prepare_certificate(root,"self_generated")
            self.assertEqual(first.fingerprint_sha256,same.fingerprint_sha256)
            self.assertEqual((root/"private/tls/server-key.pem").stat().st_mode&0o777,0o600)
            generate_certificate(root/"private/tls",replace=True)
            renewed=prepare_certificate(root,"self_generated")
            self.assertNotEqual(first.fingerprint_sha256,renewed.fingerprint_sha256)

    def test_external_paths_cannot_escape_ssl_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError,"external_certificate_path_invalid"):
                prepare_certificate(Path(temporary),"external","../cert.pem","key.pem",Path(temporary)/"ssl")


if __name__ == "__main__": unittest.main()
