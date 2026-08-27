from __future__ import annotations

from just_dev.jira import jira_fields_parameter, parse_includes, prepare_issue_view, render_issue_markdown
from just_dev.rendering import filter_safe_output, render


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


def test_safe_filter_removes_structural_personal_data_urls_and_attachment_metadata() -> None:
    safe = filter_safe_output(
        prepare_issue_view(
            _issue(),
            fields="summary,status,assignee,reporter,description",
            includes=parse_includes("comments,attachments"),
        )
    )

    assert "self" not in safe
    assert "assignee" not in safe["fields"]
    assert "reporter" not in safe["fields"]
    assert "attachment" not in safe["fields"]
    assert "author" not in safe["fields"]["comment"]["comments"][0]
    assert safe["fields"]["description"] == "Customer says the login button fails."
    assert "Customer says" in render(safe, "markdown")
