import asyncio
import os
import ssl
import tempfile
import unittest
from pathlib import Path

import httpx

from agent_execution_plane.pinned_http import PinnedAsyncHTTPTransport, normalize_certificate_sha256
from agent_execution_plane.tls import generate_certificate, prepare_certificate, stage_external_certificate


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

    def test_external_key_is_staged_privately_for_unprivileged_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/"ssl";source.mkdir();generate_certificate(source)
            certfile,keyfile=stage_external_certificate("server-cert.pem","server-key.pem",root/"private/external-tls",os.getuid(),os.getgid(),source)
            self.assertEqual(keyfile.stat().st_mode&0o777,0o600);self.assertEqual(certfile.stat().st_mode&0o777,0o644)
            self.assertEqual(prepare_certificate(root,"external",certfile.name,keyfile.name,certfile.parent).source,"external")


class PinnedTransportTests(unittest.IsolatedAsyncioTestCase):
    async def _server(self, certfile: Path, keyfile: Path, received: list[bytes]):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile)

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            request = await reader.read(4096)
            received.append(request)
            if request:
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
                await writer.drain()
            writer.close()
            await writer.wait_closed()

        return await asyncio.start_server(handler, "127.0.0.1", 0, ssl=context)

    async def test_correct_fingerprint_allows_https_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            certificate = prepare_certificate(Path(temporary), "self_generated")
            received: list[bytes] = []
            server = await self._server(certificate.certfile, certificate.keyfile, received)
            port = server.sockets[0].getsockname()[1]
            try:
                async with httpx.AsyncClient(transport=PinnedAsyncHTTPTransport(certificate.fingerprint_sha256)) as client:
                    response = await client.get(f"https://127.0.0.1:{port}/mcp")
                self.assertEqual(response.text, "ok")
                self.assertIn(b"GET /mcp", b"".join(received))
            finally:
                server.close()
                await server.wait_closed()

    async def test_wrong_fingerprint_fails_before_authorization_or_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            certificate = prepare_certificate(Path(temporary), "self_generated")
            received: list[bytes] = []
            server = await self._server(certificate.certfile, certificate.keyfile, received)
            port = server.sockets[0].getsockname()[1]
            try:
                async with httpx.AsyncClient(
                    headers={"Authorization": "Bearer must-not-leak"},
                    transport=PinnedAsyncHTTPTransport("0" * 64),
                ) as client:
                    with self.assertRaises(httpx.ConnectError):
                        await client.post(f"https://127.0.0.1:{port}/mcp", content=b"payload-must-not-leak")
                await asyncio.sleep(0)
                self.assertTrue(all(request == b"" for request in received))
            finally:
                server.close()
                await server.wait_closed()

    async def test_self_generated_https_fails_without_pin_or_trusted_ca(self):
        with tempfile.TemporaryDirectory() as temporary:
            certificate = prepare_certificate(Path(temporary), "self_generated")
            received: list[bytes] = []
            loop = asyncio.get_running_loop()
            previous_handler = loop.get_exception_handler()
            loop.set_exception_handler(lambda _loop, _context: None)
            server = await self._server(certificate.certfile, certificate.keyfile, received)
            port = server.sockets[0].getsockname()[1]
            try:
                async with httpx.AsyncClient(trust_env=False) as client:
                    with self.assertRaises(httpx.ConnectError):
                        await client.get(f"https://127.0.0.1:{port}/mcp")
                await asyncio.sleep(0)
                self.assertTrue(all(request == b"" for request in received))
            finally:
                server.close()
                await server.wait_closed()
                loop.set_exception_handler(previous_handler)

    def test_fingerprint_is_strictly_normalized(self):
        value = "ab" * 32
        displayed = "SHA256 Fingerprint=" + ":".join(value[index:index + 2] for index in range(0, 64, 2))
        self.assertEqual(normalize_certificate_sha256(displayed), value)
        with self.assertRaisesRegex(ValueError, "64_hexadecimal"):
            normalize_certificate_sha256("ab:cd")


if __name__ == "__main__": unittest.main()
