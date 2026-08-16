"""Recursive redaction used before logs, audit records, reports and exports."""

from __future__ import annotations

import re
from typing import Any, Iterable


SENSITIVE_KEY = re.compile(r"(?:authorization|token|secret|password|api[_-]?key|verifier|pepper)", re.I)
TOKEN_VALUE = re.compile(r"agw_[0-9a-f]{24}_[A-Za-z0-9_-]{43}")


def _same_json_value(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _same_json_value(item, right[key]) for key, item in left.items()
        )
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(
            _same_json_value(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _sensitive_candidates(values: Iterable[Any]) -> tuple[Any, ...]:
    candidates: list[Any] = []

    def collect(item: Any) -> None:
        candidates.append(item)
        if isinstance(item, dict):
            for key, nested in item.items():
                if isinstance(key, str):
                    collect(key)
                collect(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                collect(nested)

    for value in values:
        collect(value)
    return tuple(candidates)


def redact(value: Any, sensitive_values: Iterable[Any] = ()) -> Any:
    """Redact known secret keys/tokens and transient sensitive JSON values."""
    candidates = _sensitive_candidates(sensitive_values)
    sensitive_strings = sorted(
        {candidate for candidate in candidates if isinstance(candidate, str) and candidate},
        key=len,
        reverse=True,
    )

    def redact_string(item: str) -> str:
        redacted = TOKEN_VALUE.sub("[REDACTED]", item)
        for secret in sensitive_strings:
            redacted = redacted.replace(secret, "[REDACTED]")
        return redacted

    def visit(item: Any) -> Any:
        if any(_same_json_value(item, candidate) for candidate in candidates):
            return "[REDACTED]"
        if isinstance(item, dict):
            return {
                redact_string(str(key)): "[REDACTED]"
                if SENSITIVE_KEY.search(str(key))
                else visit(nested)
                for key, nested in item.items()
            }
        if isinstance(item, list):
            return [visit(nested) for nested in item]
        if isinstance(item, tuple):
            return tuple(visit(nested) for nested in item)
        if isinstance(item, str):
            return redact_string(item)
        return item

    return visit(value)
