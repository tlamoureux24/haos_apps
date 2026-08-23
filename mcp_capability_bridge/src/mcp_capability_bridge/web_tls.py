"""Certificate pinning against the certificate used by Chromium itself."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re


logger = logging.getLogger("mcp_capability_bridge.web_tls")


def normalize_certificate_sha256(value: object) -> str:
    compact = re.sub(r"[^0-9A-Fa-f]", "", str(value or ""))
    if not compact:
        return ""
    if len(compact) != 64 or not re.fullmatch(r"[0-9A-Fa-f]{64}", compact):
        raise ValueError("invalid_web_certificate_sha256")
    return ":".join(compact[index:index + 2].upper() for index in range(0, 64, 2))


def verify_driver_certificate(driver, origin: str, expected: object) -> None:
    fingerprint = normalize_certificate_sha256(expected)
    if not fingerprint:
        return
    response = driver.execute_cdp_cmd("Network.getCertificate", {"origin": origin})
    certificates = response.get("tableNames", []) if isinstance(response, dict) else []
    try:
        actual = hashlib.sha256(base64.b64decode(certificates[0], validate=True)).hexdigest().upper()
    except (IndexError, TypeError, ValueError) as exc:
        logger.warning("MCB_WEB_TLS_PIN rejected origin=%s code=web_certificate_unavailable", origin)
        raise RuntimeError("web_certificate_unavailable") from exc
    if not hmac.compare_digest(actual, fingerprint.replace(":", "")):
        logger.warning("MCB_WEB_TLS_PIN rejected origin=%s code=web_certificate_sha256_mismatch", origin)
        raise RuntimeError("web_certificate_sha256_mismatch")
