from __future__ import annotations

from just_dev.jira import prepare_attach_view, render_attach_markdown
from just_dev.rendering import render_markdown


def _raw_attach_result() -> dict:
    return {
        "issue_id_or_key": "DEV-1",
        "filename": "notes.txt",
        "attachments": [
            {
                "id": "20001",
                "self": "https://example.atlassian.net/rest/api/3/attachment/20001",
                "filename": "notes.txt",
                "author": {
                    "accountId": "account-1",
                    "accountType": "atlassian",
                    "displayName": "Ada",
                    "avatarUrls": {
                        "48x48": "https://example.atlassian.net/avatar/48",
                        "32x32": "https://example.atlassian.net/avatar/32",
                        "24x24": "https://example.atlassian.net/avatar/24",
                        "16x16": "https://example.atlassian.net/avatar/16",
                    },
                    "timeZone": "Europe/Vienna",
                },
                "created": "2026-08-27T10:00:00.000+0200",
                "size": 11,
                "mimeType": "text/plain",
                "content": "https://example.atlassian.net/rest/api/3/attachment/content/20001",
            }
        ],
    }


def test_prepare_attach_view_drops_the_nested_author_avatar_and_url_bulk() -> None:
    view = prepare_attach_view(_raw_attach_result())

    assert view == {
        "issue_id_or_key": "DEV-1",
        "filename": "notes.txt",
        "attachments": [{"id": "20001", "size": 11}],
    }


def test_render_attach_markdown_is_a_one_line_confirmation() -> None:
    markdown = render_attach_markdown(prepare_attach_view(_raw_attach_result()))

    assert markdown == "Attached **notes.txt** (11 bytes) to **DEV-1**."


def test_render_attach_markdown_falls_back_for_an_unexpected_shape() -> None:
    incomplete = {"issue_id_or_key": "DEV-1"}

    assert render_attach_markdown(incomplete) == render_markdown(incomplete)
