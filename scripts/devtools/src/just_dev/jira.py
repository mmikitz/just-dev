"""Jira read request policy and concise issue views."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .errors import InputValidationError
from .rendering import render_markdown

_INCLUDE_FIELDS = {"links": "issuelinks", "attachments": "attachment", "comments": "comment"}
_DEFAULT_SUMMARY_FIELDS = ("summary", "status", "assignee", "reporter", "issuetype", "priority")
_BULKY_FIELDS = frozenset(_INCLUDE_FIELDS.values())


def parse_csv(value: str | None, *, label: str) -> list[str]:
    if value is None:
        return []
    values = [item.strip() for item in value.split(",") if item.strip()]
    if value.strip() and not values:
        raise InputValidationError(f"{label} must contain at least one comma-separated value.")
    if len(set(values)) != len(values):
        raise InputValidationError(f"{label} cannot repeat values.")
    return values


def parse_includes(value: str | Sequence[str] | None) -> tuple[str, ...]:
    values = parse_csv(value, label="--include") if isinstance(value, str) else list(value or ())
    normalized = tuple(item.strip().lower() for item in values if item.strip())
    invalid = sorted(set(normalized) - set(_INCLUDE_FIELDS))
    if invalid:
        raise InputValidationError(
            "--include accepts only links, attachments, comments (unknown: " + ", ".join(invalid) + ")."
        )
    if len(set(normalized)) != len(normalized):
        raise InputValidationError("--include cannot repeat values.")
    return normalized


def validate_view(value: str) -> str:
    if value not in {"summary", "full"}:
        raise InputValidationError("--view must be 'summary' or 'full'.")
    return value


def jira_fields_parameter(
    fields: str | None,
    *,
    includes: Sequence[str] = (),
    view: str = "summary",
) -> str | None:
    """Choose a server-side field list, keeping the human default compact."""

    view = validate_view(view)
    selected = parse_csv(fields, label="--fields")
    if not selected and view == "summary":
        selected = list(_DEFAULT_SUMMARY_FIELDS)
    if selected:
        for include in includes:
            field = _INCLUDE_FIELDS[include]
            if field not in selected:
                selected.append(field)
        return ",".join(selected)
    # Jira's normal default supplies the full field set. Do not turn a full
    # view into a restrictive list merely because an include was supplied.
    return None


def prepare_issue_view(
    issue: Mapping[str, Any],
    *,
    fields: str | None = None,
    includes: Sequence[str] = (),
    view: str = "summary",
) -> dict[str, Any]:
    """Apply the user-visible view and bulky-section policy to a Jira response."""

    view = validate_view(view)
    included_fields = tuple(_INCLUDE_FIELDS[include] for include in includes)
    included_field_set = set(included_fields)
    remote_fields = issue.get("fields")
    field_data = dict(remote_fields) if isinstance(remote_fields, Mapping) else {}
    for field in _BULKY_FIELDS - included_field_set:
        field_data.pop(field, None)

    if view == "summary":
        selected = parse_csv(fields, label="--fields") or list(_DEFAULT_SUMMARY_FIELDS)
        selected.extend(field for field in included_fields if field not in selected)
        field_data = {field: field_data[field] for field in selected if field in field_data}
        result: dict[str, Any] = {}
        for key in ("id", "key"):
            if key in issue:
                result[key] = issue[key]
        result["fields"] = field_data
        return result

    result = dict(issue)
    result["fields"] = field_data
    return result


def render_issue_markdown(value: Any) -> str:
    """Give the normal Jira summary view an especially scannable Markdown form."""

    if not isinstance(value, Mapping):
        return render_markdown(value)
    fields = value.get("fields")
    if not isinstance(fields, Mapping):
        return render_markdown(value)
    key = value.get("key")
    summary = _display_value(fields.get("summary"))
    if key and summary:
        lines = [f"# {key}: {summary}"]
    elif key:
        lines = [f"# {key}"]
    else:
        lines = []
    if value.get("id"):
        lines.append(f"- **ID:** {_display_value(value['id'])}")
    for name, item in fields.items():
        if name == "summary":
            continue
        label = name.replace("_", " ").title()
        if isinstance(item, Mapping | list | tuple):
            lines.append(f"## {label}")
            lines.append(render_markdown(item))
        else:
            lines.append(f"- **{label}:** {_display_value(item)}")
    return "\n".join(lines) or render_markdown(value)


def _display_value(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("name", "key", "value", "displayName"):
            candidate = value.get(key)
            if candidate is not None:
                return str(candidate)
        return render_markdown(value)
    if value is None:
        return ""
    return str(value)
