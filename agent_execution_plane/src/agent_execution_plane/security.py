"""Authenticated encryption for provider credentials."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet


def load_or_create_key(path: Path) -> bytes:
    if path.exists():
        os.chmod(path, 0o600)
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(Fernet.generate_key())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path.read_bytes()


def encrypt(key: bytes, value: str) -> bytes:
    return Fernet(key).encrypt(value.encode())


def decrypt(key: bytes, value: bytes | None) -> str | None:
    return Fernet(key).decrypt(value).decode() if value else None
