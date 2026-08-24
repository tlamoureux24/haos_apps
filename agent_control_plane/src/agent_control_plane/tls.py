"""Persistent server-certificate management for public ACP listeners."""

from __future__ import annotations

import hashlib
import os
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


@dataclass(frozen=True)
class CertificateInfo:
    source: str
    certfile: Path
    keyfile: Path
    fingerprint_sha256: str
    subject: str
    issuer: str
    not_before: str
    not_after: str


def _write_private(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def generate_certificate(directory: Path, common_name: str, *, replace: bool = False) -> tuple[Path, Path]:
    certfile = directory / "server-cert.pem"
    keyfile = directory / "server-key.pem"
    if certfile.exists() and keyfile.exists() and not replace:
        return certfile, keyfile
    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=5 * 365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True, data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=None, decipher_only=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    _write_private(keyfile, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), 0o600)
    _write_private(certfile, certificate.public_bytes(serialization.Encoding.PEM), 0o644)
    return certfile, keyfile


def external_paths(ssl_dir: Path, cert_name: str, key_name: str) -> tuple[Path, Path]:
    if not cert_name or not key_name:
        raise ValueError("external_certificate_and_key_required")
    root = ssl_dir.resolve()
    paths = tuple((root / name).resolve() for name in (cert_name, key_name))
    if any(Path(name).is_absolute() or root not in path.parents for name, path in zip((cert_name, key_name), paths)):
        raise ValueError("external_certificate_path_invalid")
    return paths[0], paths[1]


def certificate_validity(certificate: x509.Certificate) -> tuple[datetime, datetime]:
    """Return UTC-aware validity bounds across cryptography API generations."""
    try:
        return certificate.not_valid_before_utc, certificate.not_valid_after_utc
    except AttributeError:
        return (
            certificate.not_valid_before.replace(tzinfo=timezone.utc),
            certificate.not_valid_after.replace(tzinfo=timezone.utc),
        )


def inspect_certificate(source: str, certfile: Path, keyfile: Path) -> CertificateInfo:
    certificate = x509.load_pem_x509_certificate(certfile.read_bytes())
    private_key = serialization.load_pem_private_key(keyfile.read_bytes(), password=None)
    public_format = serialization.PublicFormat.SubjectPublicKeyInfo
    if certificate.public_key().public_bytes(serialization.Encoding.DER, public_format) != private_key.public_key().public_bytes(serialization.Encoding.DER, public_format):
        raise ValueError("certificate_private_key_mismatch")
    now = datetime.now(timezone.utc)
    not_before, not_after = certificate_validity(certificate)
    if now < not_before:
        raise ValueError("certificate_not_yet_valid")
    if now > not_after:
        raise ValueError("certificate_expired")
    try:
        if certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError("ca_certificate_not_allowed")
    except x509.ExtensionNotFound:
        pass
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(certfile), str(keyfile))
    fingerprint = hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest()
    return CertificateInfo(source, certfile, keyfile, ":".join(fingerprint[i:i + 2].upper() for i in range(0, 64, 2)), certificate.subject.rfc4514_string(), certificate.issuer.rfc4514_string(), not_before.isoformat().replace("+00:00", "Z"), not_after.isoformat().replace("+00:00", "Z"))


def prepare_certificate(data_dir: Path, source: str, cert_name: str = "", key_name: str = "", ssl_dir: Path | None = None) -> CertificateInfo:
    ssl_dir = ssl_dir or Path("/ssl")
    if source == "self_generated":
        certfile, keyfile = generate_certificate(data_dir / "private" / "tls", "Agent Control Plane")
    elif source == "external":
        certfile, keyfile = external_paths(ssl_dir, cert_name, key_name)
    else:
        raise ValueError("invalid_certificate_source")
    return inspect_certificate(source, certfile, keyfile)
