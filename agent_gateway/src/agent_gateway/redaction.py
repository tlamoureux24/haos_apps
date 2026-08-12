"""Recursive redaction used before logs, audit records, reports and exports."""

from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEY = re.compile(r"(?:authorization|token|secret|password|api[_-]?key|verifier|pepper)", re.I)
TOKEN_VALUE = re.compile(r"agw_[0-9a-f]{24}_[A-Za-z0-9_-]{43}")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return TOKEN_VALUE.sub("[REDACTED]", value)
    return value
