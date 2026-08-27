"""Common, deterministic result rendering and structural safe-output filtering."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

OMITTED = "[OMITTED]"
_SAFE_KEY = re.compile(
    r"(?:account(?:id)?|email(?:address)?|displayname|avatar(?:urls?)?|"
    r"assignee|reporter|creator|author|user(?:s)?|identity|owner|watcher(?:s)?|voters?|"
    r"url|uri|href|self|attachment(?:s)?|thumbnail|filename|mime(?:type)?)$",
    re.IGNORECASE,
)
_URL_VALUE = re.compile(r"https?://\S+", re.IGNORECASE)


def _safe_key(key: object) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return (
        bool(_SAFE_KEY.fullmatch(compact)) or compact.startswith("account") or compact.endswith(("url", "uri", "href"))
    )


def filter_safe_output(value: Any) -> Any:
    """Redact structural identifiers and URL/attachment metadata from result data.

    A redacted key or standalone URL value is replaced with the ``OMITTED``
    sentinel rather than deleted, so the key set a caller sees — and any
    declared ``outputSchema`` — is unaffected by ``--safe``, and a caller can
    tell "redacted by policy" apart from "absent in the source data" (F5).

    This intentionally acts on fields and standalone URL values, not arbitrary
    prose. A description or comment can still contain personal information, so
    callers must not present ``--safe`` as a complete PII classifier.
    """

    return _filter_safe(value)


def _filter_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): OMITTED if _safe_key(key) else _filter_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_filter_safe(item) for item in value]
    if isinstance(value, str) and _URL_VALUE.fullmatch(value.strip()):
        return OMITTED
    return value


def render_text(value: Any) -> str:
    """Render nested JSON-like data as concise indented plain text."""

    lines: list[str] = []
    _text_lines(value, lines, indent=0)
    return "\n".join(lines)


def _text_lines(value: Any, lines: list[str], *, indent: int, label: str | None = None) -> None:
    prefix = "  " * indent
    if isinstance(value, Mapping):
        if label is not None:
            lines.append(f"{prefix}{label}:")
            indent += 1
            prefix = "  " * indent
        if not value:
            if label is None:
                lines.append(f"{prefix}{{}}")
            return
        for key, item in value.items():
            _text_lines(item, lines, indent=indent, label=str(key))
        return
    if isinstance(value, list | tuple):
        if label is not None:
            lines.append(f"{prefix}{label}:")
            indent += 1
            prefix = "  " * indent
        if not value:
            lines.append(f"{prefix}[]")
            return
        for item in value:
            if isinstance(item, Mapping | list | tuple):
                lines.append(f"{prefix}-")
                _text_lines(item, lines, indent=indent + 1)
            else:
                lines.append(f"{prefix}- {_scalar(item)}")
        return
    rendered = _scalar(value)
    if label is None:
        lines.append(f"{prefix}{rendered}")
    else:
        lines.append(f"{prefix}{label}: {rendered}")


def render_markdown(value: Any) -> str:
    """Render nested JSON-like data as readable Markdown without raw HTML."""

    lines: list[str] = []
    _markdown_lines(value, lines, depth=0)
    return "\n".join(lines)


def _markdown_lines(value: Any, lines: list[str], *, depth: int, label: str | None = None) -> None:
    if isinstance(value, Mapping):
        if label is not None:
            heading = "#" * min(depth + 2, 6)
            lines.append(f"{heading} {_markdown_label(label)}")
        if not value:
            lines.append("_None_")
            return
        for key, item in value.items():
            if isinstance(item, Mapping | list | tuple):
                _markdown_lines(item, lines, depth=depth + 1, label=str(key))
            else:
                lines.append(f"- **{_markdown_label(str(key))}:** {_scalar(item)}")
        return
    if isinstance(value, list | tuple):
        if label is not None:
            heading = "#" * min(depth + 2, 6)
            lines.append(f"{heading} {_markdown_label(label)}")
        if not value:
            lines.append("_None_")
            return
        for item in value:
            if isinstance(item, Mapping | list | tuple):
                _markdown_lines(item, lines, depth=depth + 1)
            else:
                lines.append(f"- {_scalar(item)}")
        return
    if label is None:
        lines.append(_scalar(value))
    else:
        lines.append(f"- **{_markdown_label(label)}:** {_scalar(value)}")


def _markdown_label(value: str) -> str:
    return value.replace("_", " ").replace("*", "\\*")


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render(value: Any, output_format: str, *, safe: bool = False) -> str:
    """Render a public result in one of the supported formats."""

    data = filter_safe_output(value) if safe else value
    if output_format == "json":
        return json.dumps(data, ensure_ascii=False, sort_keys=True)
    if output_format == "markdown":
        return render_markdown(data)
    return render_text(data)


def known_safe_output_formats() -> Sequence[str]:
    return ("text", "markdown", "json")
