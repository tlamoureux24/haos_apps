"""HTTPX transport that authenticates the exact TLS socket before HTTP writes."""

from __future__ import annotations

import hashlib
import hmac
import re
import ssl
from typing import Iterable

import httpcore
import httpx


def normalize_certificate_sha256(value: str | None) -> str:
    fingerprint = str(value or "").strip()
    fingerprint = re.sub(r"^sha256\s+fingerprint\s*=\s*", "", fingerprint, flags=re.I)
    fingerprint = fingerprint.replace(":", "").replace(" ", "").lower()
    if fingerprint and not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("certificate_sha256_must_contain_64_hexadecimal_characters")
    return fingerprint


class _PinnedStream(httpcore.AsyncNetworkStream):
    def __init__(self, stream: httpcore.AsyncNetworkStream, expected: str) -> None:
        self.stream, self.expected = stream, expected

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return await self.stream.read(max_bytes, timeout)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        await self.stream.write(buffer, timeout)

    async def aclose(self) -> None:
        await self.stream.aclose()

    async def start_tls(self, ssl_context: ssl.SSLContext, server_hostname: str | None = None, timeout: float | None = None) -> httpcore.AsyncNetworkStream:
        stream = await self.stream.start_tls(ssl_context, server_hostname, timeout)
        ssl_object = stream.get_extra_info("ssl_object")
        certificate = ssl_object.getpeercert(binary_form=True) if ssl_object else b""
        actual = hashlib.sha256(certificate).hexdigest()
        if not certificate or not hmac.compare_digest(actual, self.expected):
            await stream.aclose()
            raise httpcore.ConnectError("certificate_sha256_mismatch")
        return _PinnedStream(stream, self.expected)

    def get_extra_info(self, info: str):
        return self.stream.get_extra_info(info)


class _PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, expected: str) -> None:
        self.backend, self.expected = httpcore.AnyIOBackend(), expected

    async def connect_tcp(self, host: str, port: int, timeout: float | None = None, local_address: str | None = None, socket_options: Iterable | None = None) -> httpcore.AsyncNetworkStream:
        return _PinnedStream(await self.backend.connect_tcp(host, port, timeout, local_address, socket_options), self.expected)

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options: Iterable | None = None) -> httpcore.AsyncNetworkStream:
        return _PinnedStream(await self.backend.connect_unix_socket(path, timeout, socket_options), self.expected)

    async def sleep(self, seconds: float) -> None:
        await self.backend.sleep(seconds)


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self, fingerprint: str) -> None:
        expected = normalize_certificate_sha256(fingerprint)
        if not expected:
            raise ValueError("certificate_sha256_required")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        super().__init__(verify=context, trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(ssl_context=context, network_backend=_PinnedBackend(expected))


def async_client_kwargs(fingerprint: str | None) -> dict[str, object]:
    normalized = normalize_certificate_sha256(fingerprint)
    return {"transport": PinnedAsyncHTTPTransport(normalized)} if normalized else {}
