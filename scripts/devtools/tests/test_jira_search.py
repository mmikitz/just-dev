from __future__ import annotations

from just_dev.jira import prepare_search_view, render_search_markdown
from just_dev.rendering import filter_safe_output, render


def _search_response() -> dict:
    return {
        "issues": [
            {
                "id": "10001",
                "key": "DEV-1",
                "self": "https://example.atlassian.net/rest/api/3/issue/10001",
                "fields": {
                    "summary": "Investigate login failure",
                    "status": {"name": "In Progress"},
                    "assignee": {"displayName": "Ada", "accountId": "account-1"},
                    "reporter": {"displayName": "Grace", "accountId": "account-2"},
                    "description": "Customer says the login button fails.",
                },
            },
            {
                "id": "10002",
                "key": "DEV-2",
                "self": "https://example.atlassian.net/rest/api/3/issue/10002",
                "fields": {
                    "summary": "Add pagination to search",
                    "status": {"name": "To Do"},
                    "assignee": None,
                    "reporter": {"displayName": "Grace", "accountId": "account-2"},
                },
            },
        ],
        "nextPageToken": "CAEaAggD",
        "isLast": False,
    }


def test_prepare_search_view_default_summary_selects_concise_fields_per_issue() -> None:
    view = prepare_search_view(_search_response())

    assert [issue["key"] for issue in view["issues"]] == ["DEV-1", "DEV-2"]
    assert set(view["issues"][0]["fields"]) == {"summary", "status", "assignee", "reporter"}
    assert "description" not in view["issues"][0]["fields"]
    assert view["nextPageToken"] == "CAEaAggD"
    assert view["isLast"] is False


def test_prepare_search_view_full_view_keeps_the_complete_per_issue_payload() -> None:
    view = prepare_search_view(_search_response(), view="full")

    assert view["issues"][0]["fields"]["description"] == "Customer says the login button fails."
    assert view["issues"][0]["self"] == "https://example.atlassian.net/rest/api/3/issue/10001"


def test_prepare_search_view_explicit_fields_wins_over_the_default_summary_set() -> None:
    view = prepare_search_view(_search_response(), fields="summary")

    assert set(view["issues"][0]["fields"]) == {"summary"}


def test_prepare_search_view_handles_an_empty_result_set() -> None:
    view = prepare_search_view({"issues": [], "isLast": True})

    assert view == {"issues": [], "isLast": True}


def test_render_search_markdown_lists_one_scannable_line_per_issue() -> None:
    markdown = render_search_markdown(prepare_search_view(_search_response()))

    assert "**DEV-1**: Investigate login failure — In Progress, Ada" in markdown
    assert "**DEV-2**: Add pagination to search — To Do, Unassigned" in markdown
    assert "_Next page token: CAEaAggD_" in markdown


def test_render_search_markdown_reports_no_issues_found() -> None:
    markdown = render_search_markdown(prepare_search_view({"issues": []}))

    assert markdown == "_No issues found._"


def test_render_search_markdown_omits_the_next_page_note_when_absent() -> None:
    markdown = render_search_markdown(prepare_search_view({"issues": [], "isLast": True}))

    assert "Next page token" not in markdown


def test_safe_filter_strips_assignee_reporter_and_urls_from_every_issue() -> None:
    safe = filter_safe_output(prepare_search_view(_search_response(), view="full"))

    assert "self" not in safe["issues"][0]
    assert "assignee" not in safe["issues"][0]["fields"]
    assert "reporter" not in safe["issues"][0]["fields"]
    assert safe["issues"][0]["fields"]["description"] == "Customer says the login button fails."
    assert "Investigate login failure" in render(safe, "markdown")
