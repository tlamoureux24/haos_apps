"""Persistent TLS server identity for Agent Execution Plane."""
from __future__ import annotations
import hashlib, os, ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

@dataclass(frozen=True)
class CertificateInfo:
    source:str;certfile:Path;keyfile:Path;fingerprint_sha256:str;subject:str;issuer:str;not_before:str;not_after:str

def _write(path:Path,data:bytes,mode:int):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True);tmp=path.with_name(f".{path.name}.{os.getpid()}.tmp");fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
    try:
        with os.fdopen(fd,"wb") as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:
        try:tmp.unlink()
        except FileNotFoundError:pass

def generate_certificate(directory:Path,*,replace=False):
    cert,keyfile=directory/"server-cert.pem",directory/"server-key.pem"
    if cert.exists() and keyfile.exists() and not replace:return cert,keyfile
    now=datetime.now(timezone.utc);key=rsa.generate_private_key(public_exponent=65537,key_size=2048);name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"Agent Execution Plane")])
    value=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=1825)).add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False).add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=True,data_encipherment=False,key_agreement=False,key_cert_sign=False,crl_sign=False,encipher_only=None,decipher_only=None),critical=True).sign(key,hashes.SHA256()))
    _write(keyfile,key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()),0o600);_write(cert,value.public_bytes(serialization.Encoding.PEM),0o644);return cert,keyfile

def external_paths(root:Path,cert_name:str,key_name:str):
    if not cert_name or not key_name:raise ValueError("external_certificate_and_key_required")
    base=root.resolve();paths=[(base/name).resolve() for name in (cert_name,key_name)]
    if any(Path(name).is_absolute() or base not in path.parents for name,path in zip((cert_name,key_name),paths)):raise ValueError("external_certificate_path_invalid")
    return paths

def stage_external_certificate(cert_name:str,key_name:str,directory:Path,uid:int,gid:int,source_root:Path=Path("/ssl")):
    sources=external_paths(source_root,cert_name,key_name);directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():raise ValueError("external_certificate_stage_invalid")
    certfile,keyfile=directory/"server-cert.pem",directory/"server-key.pem"
    for path in (certfile,keyfile):
        try:path.unlink()
        except FileNotFoundError:pass
    inspect_certificate("external",*sources)
    _write(certfile,sources[0].read_bytes(),0o644);_write(keyfile,sources[1].read_bytes(),0o600)
    os.chown(directory,uid,gid);os.chown(certfile,uid,gid);os.chown(keyfile,uid,gid)
    return certfile,keyfile

def inspect_certificate(source:str,certfile:Path,keyfile:Path):
    cert=x509.load_pem_x509_certificate(certfile.read_bytes());key=serialization.load_pem_private_key(keyfile.read_bytes(),None);fmt=serialization.PublicFormat.SubjectPublicKeyInfo
    if cert.public_key().public_bytes(serialization.Encoding.DER,fmt)!=key.public_key().public_bytes(serialization.Encoding.DER,fmt):raise ValueError("certificate_private_key_mismatch")
    now=datetime.now(timezone.utc);before,after=cert.not_valid_before_utc,cert.not_valid_after_utc
    if now<before:raise ValueError("certificate_not_yet_valid")
    if now>after:raise ValueError("certificate_expired")
    try:
        if cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:raise ValueError("ca_certificate_not_allowed")
    except x509.ExtensionNotFound:pass
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.minimum_version=ssl.TLSVersion.TLSv1_2;context.load_cert_chain(certfile,keyfile)
    raw=hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest();return CertificateInfo(source,certfile,keyfile,":".join(raw[i:i+2].upper() for i in range(0,64,2)),cert.subject.rfc4514_string(),cert.issuer.rfc4514_string(),before.isoformat().replace("+00:00","Z"),after.isoformat().replace("+00:00","Z"))

def prepare_certificate(data_dir:Path,source:str,cert_name="",key_name="",ssl_dir:Path|None=None):
    ssl_dir=ssl_dir or Path(os.environ.get("AGENT_EXECUTION_PLANE_EXTERNAL_TLS_DIR","/ssl"))
    paths=generate_certificate(data_dir/"private"/"tls") if source=="self_generated" else external_paths(ssl_dir,cert_name,key_name) if source=="external" else (_ for _ in ()).throw(ValueError("invalid_certificate_source"))
    return inspect_certificate(source,*paths)
