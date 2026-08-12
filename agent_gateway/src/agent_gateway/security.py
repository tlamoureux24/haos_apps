"""Credential creation and verification without retaining plaintext secrets."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path


TOKEN_PATTERN = re.compile(r"^agw_([0-9a-f]{24})_([A-Za-z0-9_-]{43})$")


@dataclass(frozen=True)
class IssuedCredential:
    credential_id: str
    token: str
    verifier: str


def load_or_create_pepper(path: Path) -> bytes:
    configured = os.environ.get("AGENT_GATEWAY_CREDENTIAL_PEPPER_HEX")
    if configured is not None:
        try:
            pepper = bytes.fromhex(configured)
        except ValueError as err:
            raise RuntimeError("Configured credential pepper is invalid") from err
        if len(pepper) != 32:
            raise RuntimeError("Configured credential pepper has an invalid length")
        return pepper
    try:
        pepper = path.read_bytes()
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
                pepper = path.read_bytes()
            else:
                pepper = candidate
        finally:
            temporary.unlink(missing_ok=True)
    if len(pepper) != 32:
        raise RuntimeError("Credential pepper has an invalid length")
    return pepper


def credential_verifier(pepper: bytes, secret: str) -> str:
    return hmac.new(pepper, secret.encode("ascii"), hashlib.sha256).hexdigest()


def issue_credential(pepper: bytes) -> IssuedCredential:
    credential_id = secrets.token_hex(12)
    secret = secrets.token_urlsafe(32)
    return IssuedCredential(
        credential_id=credential_id,
        token=f"agw_{credential_id}_{secret}",
        verifier=credential_verifier(pepper, secret),
    )


def token_credential_id(token: str) -> str | None:
    match = TOKEN_PATTERN.fullmatch(token)
    return match.group(1) if match else None


def parse_and_verify_token(token: str, pepper: bytes, expected_verifier: str) -> str | None:
    match = TOKEN_PATTERN.fullmatch(token)
    if not match:
        return None
    credential_id, secret = match.groups()
    actual = credential_verifier(pepper, secret)
    if not hmac.compare_digest(actual, expected_verifier):
        return None
    return credential_id
