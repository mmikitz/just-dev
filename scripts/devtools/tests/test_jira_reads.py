from __future__ import annotations

import pytest

from just_dev.errors import InputValidationError
from just_dev.jira import jira_fields_parameter, parse_includes, prepare_issue_view, render_issue_markdown
from just_dev.rendering import OMITTED, filter_safe_output, render


def _issue() -> dict:
    return {
        "id": "10001",
        "key": "DEV-1",
        "self": "https://example.atlassian.net/rest/api/3/issue/10001",
        "fields": {
            "summary": "Investigate login failure",
            "status": {"name": "In Progress"},
            "assignee": {"displayName": "Ada", "accountId": "account-1"},
            "reporter": {"displayName": "Grace", "accountId": "account-2"},
            "description": "Customer says the login button fails.",
            "issuelinks": [{"type": {"name": "blocks"}, "outwardIssue": {"key": "DEV-2"}}],
            "attachment": [{"filename": "screen.png", "content": "https://files.example/screen.png"}],
            "comment": {"comments": [{"author": {"displayName": "Ada"}, "body": "Please investigate."}]},
        },
    }


def test_jira_summary_view_requests_and_returns_only_concise_opted_in_sections() -> None:
    includes = parse_includes("comments,links")

    fields = jira_fields_parameter(None, includes=includes, view="summary")
    view = prepare_issue_view(_issue(), includes=includes, view="summary")

    assert fields == "summary,status,assignee,reporter,issuetype,priority,comment,issuelinks"
    assert set(view["fields"]) == {"summary", "status", "assignee", "reporter", "comment", "issuelinks"}
    assert "attachment" not in view["fields"]
    assert render_issue_markdown(view).startswith("# DEV-1: Investigate login failure")


def test_render_issue_markdown_keeps_identity_fields_compact() -> None:
    markdown = render_issue_markdown(prepare_issue_view(_issue(), view="summary"))

    assert "- **Status:** In Progress" in markdown
    assert "- **Assignee:** Ada" in markdown
    assert "- **Reporter:** Grace" in markdown
    assert "## Status" not in markdown
    assert "## Assignee" not in markdown
    assert "accountId" not in markdown


def test_jira_full_view_keeps_regular_fields_but_requires_explicit_bulky_includes() -> None:
    view = prepare_issue_view(_issue(), fields="summary,description", includes=(), view="full")

    assert view["fields"]["description"] == "Customer says the login button fails."
    assert "attachment" not in view["fields"]
    assert "comment" not in view["fields"]
    assert "issuelinks" not in view["fields"]


def test_jira_summary_view_carries_expand_keys_through_when_present() -> None:
    issue = _issue()
    issue["changelog"] = {"histories": [{"id": "10050", "items": []}]}
    issue["names"] = {"summary": "Summary"}
    issue["schema"] = {"summary": {"type": "string", "system": "summary"}}

    view = prepare_issue_view(issue, view="summary")

    assert view["changelog"] == {"histories": [{"id": "10050", "items": []}]}
    assert view["names"] == {"summary": "Summary"}
    assert view["schema"] == {"summary": {"type": "string", "system": "summary"}}


def test_jira_summary_view_has_no_expand_keys_when_none_were_requested() -> None:
    # --expand only ever puts changelog/names/schema on the raw response, so a
    # plain issue (no --expand) must come back with exactly id/key/fields and
    # nothing else, unchanged from before F3.
    view = prepare_issue_view(_issue(), view="summary")

    assert set(view) == {"id", "key", "fields"}


def _minimal_issue() -> dict:
    return {
        "id": "10002",
        "key": "DEV-2",
        "fields": {"summary": "Only summary came back"},
    }


def test_jira_summary_view_rejects_a_fields_typo_absent_from_the_response() -> None:
    with pytest.raises(InputValidationError, match="typoField"):
        prepare_issue_view(_minimal_issue(), fields="summary,typoField", view="summary")


def test_jira_summary_view_fields_validation_survives_a_non_mapping_fields_payload() -> None:
    issue = {"id": "10003", "key": "DEV-3"}  # no "fields" key at all

    with pytest.raises(InputValidationError, match="typoField"):
        prepare_issue_view(issue, fields="typoField", view="summary")


def test_jira_summary_view_does_not_flag_a_field_only_suppressed_by_missing_include() -> None:
    # "comment" is present in the raw Jira response but --include comments was
    # not passed, so the bulky-section policy (not a typo) is why it is
    # missing from the result; --fields validation must not raise for it.
    view = prepare_issue_view(_issue(), fields="comment", view="summary")

    assert view["fields"] == {}


def test_jira_summary_view_default_fields_are_unaffected_by_the_new_fields_validation() -> None:
    view = prepare_issue_view(_issue())

    assert set(view["fields"]) == {"summary", "status", "assignee", "reporter"}


def test_safe_filter_removes_structural_personal_data_urls_and_attachment_metadata() -> None:
    safe = filter_safe_output(
        prepare_issue_view(
            _issue(),
            fields="summary,status,assignee,reporter,description",
            includes=parse_includes("comments,attachments"),
        )
    )

    assert "self" not in safe
    assert safe["fields"]["assignee"] == OMITTED
    assert safe["fields"]["reporter"] == OMITTED
    # The attachment list itself is structural, not PII, and must survive so
    # --include attachments --safe still shows something; only its nested
    # PII/URL leaves (e.g. "content") are redacted in place.
    assert safe["fields"]["attachment"] == [{"filename": "screen.png", "content": OMITTED}]
    assert safe["fields"]["comment"]["comments"][0]["author"] == OMITTED
    assert safe["fields"]["description"] == "Customer says the login button fails."
    assert "Customer says" in render(safe, "markdown")


def test_safe_filter_keeps_attach_jira_issues_own_top_level_result_shape() -> None:
    # attach-jira-issue's result uses "filename"/"attachments" as its own
    # top-level keys, which happen to collide with the same names used as
    # nested PII/bulk leaves elsewhere. --safe must still confirm the attach
    # succeeded instead of reducing the result to just the issue key.
    safe = filter_safe_output(
        {
            "issue_id_or_key": "DEV-1",
            "filename": "notes.txt",
            "attachments": [
                {
                    "id": "20001",
                    "filename": "notes.txt",
                    "author": {"displayName": "Ada", "accountId": "account-1"},
                    "content": "https://example.atlassian.net/rest/api/3/attachment/content/20001",
                }
            ],
        }
    )

    assert safe["issue_id_or_key"] == "DEV-1"
    assert safe["filename"] == "notes.txt"
    assert safe["attachments"] == [{"id": "20001", "filename": "notes.txt", "author": OMITTED, "content": OMITTED}]
