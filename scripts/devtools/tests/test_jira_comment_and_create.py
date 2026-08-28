from __future__ import annotations

from just_dev.jira import prepare_comment_view, prepare_create_view, render_comment_markdown, render_create_markdown
from just_dev.rendering import render_markdown


def _raw_comment_result() -> dict:
    """Jira's actual add-comment response: no issue key/id of its own, and an
    author/updateAuthor pair each carrying an email address and four avatar URLs."""
    author = {
        "accountId": "account-1",
        "accountType": "atlassian",
        "emailAddress": "ada@example.test",
        "displayName": "Ada",
        "avatarUrls": {
            "48x48": "https://example.atlassian.net/avatar/48",
            "32x32": "https://example.atlassian.net/avatar/32",
            "24x24": "https://example.atlassian.net/avatar/24",
            "16x16": "https://example.atlassian.net/avatar/16",
        },
    }
    return {
        "self": "https://example.atlassian.net/rest/api/3/issue/10010/comment/10000",
        "id": "10000",
        "author": author,
        "updateAuthor": author,
        "body": {"type": "doc", "version": 1, "content": []},
        "created": "2026-08-27T10:00:00.000+0200",
        "updated": "2026-08-27T10:00:00.000+0200",
    }


def test_prepare_comment_view_drops_the_nested_author_email_and_avatar_bulk() -> None:
    view = prepare_comment_view(_raw_comment_result())

    assert view == {"id": "10000"}


def test_prepare_comment_view_keeps_an_issue_reference_cli_folded_in() -> None:
    """cli.py enriches the raw response with the already-known issue_id_or_key (see
    jira.py::prepare_comment_view) before this trims it down; that field must survive."""
    enriched = {**_raw_comment_result(), "issue_id_or_key": "DEV-1"}

    view = prepare_comment_view(enriched)

    assert view == {"issue_id_or_key": "DEV-1", "id": "10000"}


def test_render_comment_markdown_names_the_issue_when_known() -> None:
    markdown = render_comment_markdown({"issue_id_or_key": "DEV-1", "id": "10000"})

    assert markdown == "Added comment **10000** to **DEV-1**."


def test_render_comment_markdown_omits_the_issue_clause_when_not_known() -> None:
    markdown = render_comment_markdown({"id": "10000"})

    assert markdown == "Added comment **10000**."


def test_render_comment_markdown_falls_back_for_an_unexpected_shape() -> None:
    incomplete = {"issue_id_or_key": "DEV-1"}

    assert render_comment_markdown(incomplete) == render_markdown(incomplete)


def _raw_create_result() -> dict:
    return {
        "id": "10005",
        "key": "DEV-42",
        "self": "https://example.atlassian.net/rest/api/3/issue/10005",
    }


def test_prepare_create_view_keeps_id_key_and_self() -> None:
    view = prepare_create_view(_raw_create_result())

    assert view == {"id": "10005", "key": "DEV-42", "self": "https://example.atlassian.net/rest/api/3/issue/10005"}


def test_prepare_create_view_drops_anything_beyond_id_key_and_self() -> None:
    bulkier = {**_raw_create_result(), "transition": {"status": 200, "errorCollection": {}}}

    view = prepare_create_view(bulkier)

    assert view == {"id": "10005", "key": "DEV-42", "self": "https://example.atlassian.net/rest/api/3/issue/10005"}


def test_render_create_markdown_is_a_one_line_confirmation() -> None:
    markdown = render_create_markdown(prepare_create_view(_raw_create_result()))

    assert markdown == "Created **DEV-42** (https://example.atlassian.net/rest/api/3/issue/10005)."


def test_render_create_markdown_omits_the_link_clause_when_not_known() -> None:
    markdown = render_create_markdown({"id": "10005", "key": "DEV-42"})

    assert markdown == "Created **DEV-42**."


def test_render_create_markdown_falls_back_for_an_unexpected_shape() -> None:
    incomplete = {"id": "10005"}

    assert render_create_markdown(incomplete) == render_markdown(incomplete)
