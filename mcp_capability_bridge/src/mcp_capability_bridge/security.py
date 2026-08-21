"""Opaque namespace credentials and separate target-secret encryption keys."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

TOKEN_PATTERN = re.compile(
    r"^mcb_([0-9a-f]{32})_([0-9a-f]{24})_([A-Za-z0-9_-]{43})$"
)


def load_or_create_key(path: Path) -> bytes:
    """Load or atomically create one exact 256-bit private key."""
    try:
        key = path.read_bytes()
    except FileNotFoundError:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        candidate = secrets.token_bytes(32)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(candidate)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                key = path.read_bytes()
            else:
                key = candidate
        finally:
            temporary.unlink(missing_ok=True)
    if len(key) != 32:
        raise RuntimeError(f"Private key has invalid length: {path.name}")
    return key


@dataclass(frozen=True)
class IssuedCredential:
    credential_id: str
    token: str
    verifier: str


def issue_credential(namespace_id: str, pepper: bytes) -> IssuedCredential:
    credential_id = secrets.token_hex(12)
    secret = secrets.token_urlsafe(32)
    token = f"mcb_{namespace_id}_{credential_id}_{secret}"
    verifier = hmac.new(pepper, token.encode("ascii"), hashlib.sha256).hexdigest()
    return IssuedCredential(credential_id, token, verifier)


def token_lookup(token: str) -> tuple[str, str] | None:
    match = TOKEN_PATTERN.fullmatch(token)
    if match is None:
        return None
    return match.group(1), match.group(2)


def verify_token(token: str, pepper: bytes, expected_verifier: str) -> bool:
    if TOKEN_PATTERN.fullmatch(token) is None:
        return False
    actual = hmac.new(pepper, token.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(actual, expected_verifier)


class SecretBox:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("invalid_secret_key")
        self._fernet = Fernet(base64.urlsafe_b64encode(key))

    def encrypt(self, value: bytes) -> bytes:
        return self._fernet.encrypt(value)

    def decrypt(self, envelope: bytes) -> bytes:
        try:
            return self._fernet.decrypt(envelope)
        except InvalidToken as exc:
            raise ValueError("invalid_secret_envelope") from exc
