"""Token-safe rendering for diagnostics, logs, and broker errors."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"
_AUTH_HEADER = re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer|basic)\s+[^\s,;]+")
_TOKEN_ASSIGNMENT = re.compile(r"(?i)\b(token|password|secret|api[_-]?key)\b\s*([:=])\s*([^\s,;]+)")
_URL_CREDENTIALS = re.compile(r"(https?://)[^\s/@:]+:[^\s/@]+@")
_SENSITIVE_KEY = re.compile(r"(?i)(token|password|secret|api[_-]?key|authorization)")


def redact_text(value: object, known_secrets: Sequence[str] = ()) -> str:
    """Return a safe string, including when a remote server echoes a token."""

    text = str(value)
    for secret in known_secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    text = _AUTH_HEADER.sub(r"\1" + REDACTED, text)
    text = _TOKEN_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
    return _URL_CREDENTIALS.sub(r"\1" + REDACTED + "@", text)


def redact_data(value: Any, known_secrets: Sequence[str] = ()) -> Any:
    """Recursively redact mapping fields while retaining useful diagnostics."""

    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if _SENSITIVE_KEY.search(str(key)) else redact_data(item, known_secrets)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_data(item, known_secrets) for item in value]
    if isinstance(value, str):
        return redact_text(value, known_secrets)
    return value
