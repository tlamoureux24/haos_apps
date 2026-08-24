from __future__ import annotations

import os
import asyncio
import ssl
import tempfile
import unittest
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from agent_control_plane.tls import certificate_validity, external_paths, generate_certificate, inspect_certificate, stage_external_certificate
from agent_control_plane.pinned_http import PinnedAsyncHTTPTransport, normalize_certificate_sha256
import httpx


class ServerCertificateTests(unittest.TestCase):
    def test_legacy_cryptography_validity_is_normalized_to_utc(self) -> None:
        before = datetime(2026, 1, 1)
        after = datetime(2027, 1, 1)
        self.assertEqual(
            certificate_validity(SimpleNamespace(not_valid_before=before, not_valid_after=after)),
            (before.replace(tzinfo=timezone.utc), after.replace(tzinfo=timezone.utc)),
        )

    def test_generated_identity_is_persistent_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certfile, keyfile = generate_certificate(root, "ACP test")
            first = inspect_certificate("self_generated", certfile, keyfile)
            certfile2, keyfile2 = generate_certificate(root, "ACP test")
            second = inspect_certificate("self_generated", certfile2, keyfile2)
            self.assertEqual(first.fingerprint_sha256, second.fingerprint_sha256)
            self.assertEqual(os.stat(keyfile).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(root).st_mode & 0o777, 0o700)

    def test_regeneration_changes_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            certfile, keyfile = generate_certificate(root, "ACP test")
            first = inspect_certificate("self_generated", certfile, keyfile)
            certfile, keyfile = generate_certificate(root, "ACP test", replace=True)
            self.assertNotEqual(first.fingerprint_sha256, inspect_certificate("self_generated", certfile, keyfile).fingerprint_sha256)

    def test_external_paths_are_confined(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(external_paths(root, "cert.pem", "key.pem"), (root / "cert.pem", root / "key.pem"))
            for name in ("../cert.pem", "/tmp/cert.pem"):
                with self.assertRaisesRegex(ValueError, "path_invalid"):
                    external_paths(root, name, "key.pem")

    def test_external_key_is_staged_privately_for_unprivileged_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"ssl";source.mkdir();generate_certificate(source,"ACP external")
            certfile,keyfile=stage_external_certificate("server-cert.pem","server-key.pem",root/"private/external-tls",os.getuid(),os.getgid(),source)
            self.assertEqual(keyfile.stat().st_mode&0o777,0o600);self.assertEqual(certfile.stat().st_mode&0o777,0o644)
            self.assertEqual(inspect_certificate("external",certfile,keyfile).source,"external")

    def test_expired_certificate_is_rejected_before_listener_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); root.chmod(0o700)
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "expired")])
            now = datetime.now(timezone.utc)
            certificate = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=2)).not_valid_after(now - timedelta(days=1)).sign(key, hashes.SHA256())
            certfile, keyfile = root / "cert.pem", root / "key.pem"
            certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
            keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            with self.assertRaisesRegex(ValueError, "certificate_expired"):
                inspect_certificate("external", certfile, keyfile)


class PinnedTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_fingerprint_is_rejected_before_authorization_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            certfile, keyfile = generate_certificate(Path(directory), "localhost")
            received: list[bytes] = []
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(certfile, keyfile)

            async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                received.append(await reader.read(4096)); writer.close(); await writer.wait_closed()

            server = await asyncio.start_server(handler, "127.0.0.1", 0, ssl=context)
            port = server.sockets[0].getsockname()[1]
            try:
                async with httpx.AsyncClient(headers={"Authorization": "Bearer secret"}, transport=PinnedAsyncHTTPTransport("0" * 64)) as client:
                    with self.assertRaises(httpx.ConnectError):
                        await client.get(f"https://127.0.0.1:{port}/mcp")
                await asyncio.sleep(0)
                self.assertTrue(all(item == b"" for item in received))
            finally:
                server.close(); await server.wait_closed()

    def test_fingerprint_normalization(self) -> None:
        value = "ab" * 32
        self.assertEqual(normalize_certificate_sha256("SHA256 Fingerprint=" + ":".join(value[i:i + 2] for i in range(0, 64, 2))), value)


if __name__ == "__main__":
    unittest.main()
