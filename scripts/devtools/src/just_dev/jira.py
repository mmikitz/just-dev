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
    full_view_sentinel: str | None = None,
) -> str | None:
    """Choose a server-side field list, keeping the human default compact.

    ``full_view_sentinel``, when given, is returned verbatim for a full view
    with no explicit fields, instead of omitting the parameter. Some
    endpoints (e.g. ``search/jql``) return no fields at all when ``fields``
    is omitted, unlike the single-issue read endpoint, whose own default
    already is the full field set.
    """

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
    if view == "full" and full_view_sentinel:
        return full_view_sentinel
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
        explicit_fields = parse_csv(fields, label="--fields")
        if explicit_fields:
            # Jira silently drops unknown field names from its own response instead of
            # erroring, so a typo'd --fields value would otherwise degrade to an empty
            # (or near-empty) result with no indication anything was wrong. Compare
            # against the *raw* response fields (before the bulky-section pop above) so
            # a legitimate field withheld only because its --include wasn't passed is
            # never mistaken for a typo.
            remote_field_names = set(remote_fields) if isinstance(remote_fields, Mapping) else set()
            unknown = sorted(set(explicit_fields) - remote_field_names)
            if unknown:
                raise InputValidationError(
                    "--fields requested field(s) Jira did not return (unknown: " + ", ".join(unknown) + ")."
                )
        selected = explicit_fields or list(_DEFAULT_SUMMARY_FIELDS)
        selected.extend(field for field in included_fields if field not in selected)
        field_data = {field: field_data[field] for field in selected if field in field_data}
        result: dict[str, Any] = {}
        for key in ("id", "key", "changelog", "names", "schema"):
            if key in issue:
                result[key] = issue[key]
        result["fields"] = field_data
        return result

    result = dict(issue)
    result["fields"] = field_data
    return result


def prepare_search_view(
    response: Mapping[str, Any],
    *,
    fields: str | None = None,
    view: str = "summary",
) -> dict[str, Any]:
    """Apply the per-issue view policy to every issue in a Jira search response."""

    view = validate_view(view)
    issues = response.get("issues")
    prepared_issues = (
        [prepare_issue_view(issue, fields=fields, view=view) for issue in issues if isinstance(issue, Mapping)]
        if isinstance(issues, list)
        else []
    )
    result: dict[str, Any] = {"issues": prepared_issues}
    for key in ("nextPageToken", "isLast", "total"):
        if key in response:
            result[key] = response[key]
    return result


def render_search_markdown(value: Any) -> str:
    """A scannable one-line-per-issue Markdown list for search results."""

    if not isinstance(value, Mapping):
        return render_markdown(value)
    issues = value.get("issues")
    if not isinstance(issues, list):
        return render_markdown(value)
    if not issues:
        lines = ["_No issues found._"]
    else:
        lines = [_search_issue_line(issue) for issue in issues if isinstance(issue, Mapping)]
    next_page_token = value.get("nextPageToken")
    if next_page_token:
        lines.append(f"_Next page token: {next_page_token}_")
    return "\n".join(lines)


def _search_issue_line(issue: Mapping[str, Any]) -> str:
    fields = issue.get("fields")
    fields = fields if isinstance(fields, Mapping) else {}
    key = _display_value(issue.get("key")) or "(no key)"
    summary = _display_value(fields.get("summary")) or "(no summary)"
    status = _display_value(fields.get("status")) or "Unknown"
    assignee = _display_value(fields.get("assignee")) or "Unassigned"
    return f"- **{key}**: {summary} — {status}, {assignee}"


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
        # A Mapping with a name/key/value/displayName (status, assignee, priority...) is an
        # identity lookup, not a bulky payload; show its label inline instead of expanding it.
        needs_expansion = isinstance(item, list | tuple) or (
            isinstance(item, Mapping) and _identity_label(item) is None
        )
        if needs_expansion:
            lines.append(f"## {label}")
            lines.append(render_markdown(item))
        else:
            lines.append(f"- **{label}:** {_display_value(item)}")
    return "\n".join(lines) or render_markdown(value)


def _identity_label(value: Mapping[str, Any]) -> str | None:
    """The human-readable label a Jira identity/lookup object (status, user, priority...) carries."""

    for key in ("name", "key", "value", "displayName"):
        candidate = value.get(key)
        if candidate is not None:
            return str(candidate)
    return None


def _display_value(value: Any) -> str:
    if isinstance(value, Mapping):
        label = _identity_label(value)
        return label if label is not None else render_markdown(value)
    if value is None:
        return ""
    return str(value)


_ATTACHMENT_SUMMARY_FIELDS = ("id", "size")


def prepare_attach_view(value: Mapping[str, Any]) -> dict[str, Any]:
    """Condense a raw Jira attach-file response to the fields that confirm success.

    Jira's created-attachment objects carry the same nested author/avatar/URL
    bulk that read-jira-issue already collapses for its own view; the useful
    confirmation here is just which file landed on which issue.
    """

    result = {key: value[key] for key in ("issue_id_or_key", "filename") if key in value}
    attachments = value.get("attachments")
    if isinstance(attachments, list):
        result["attachments"] = [
            {key: item[key] for key in _ATTACHMENT_SUMMARY_FIELDS if key in item}
            for item in attachments
            if isinstance(item, Mapping)
        ]
    return result


def render_attach_markdown(value: Any) -> str:
    """A one-line Markdown confirmation for attach-jira-issue, instead of a raw API dump."""

    if not isinstance(value, Mapping):
        return render_markdown(value)
    issue = value.get("issue_id_or_key")
    filename = value.get("filename")
    if not issue or not filename:
        return render_markdown(value)
    attachments = value.get("attachments")
    size = attachments[0].get("size") if isinstance(attachments, list) and attachments else None
    detail = f" ({size} bytes)" if size is not None else ""
    return f"Attached **{filename}**{detail} to **{issue}**."
