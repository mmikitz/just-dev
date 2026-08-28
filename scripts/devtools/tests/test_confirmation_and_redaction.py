from __future__ import annotations

import pytest

from just_dev.confirmation import confirm_mutation
from just_dev.errors import ConfirmationError
from just_dev.redaction import REDACTED, redact_data, redact_text


def test_confirmation_fails_closed_without_tty() -> None:
    with pytest.raises(ConfirmationError, match="--yes"):
        confirm_mutation("write a page", is_tty=False)


def test_dry_run_does_not_need_confirmation() -> None:
    assert confirm_mutation("write a page", dry_run=True, is_tty=False) is False


def test_token_redaction_handles_known_tokens_headers_and_mapping_keys() -> None:
    token = "very-secret-token"
    result = redact_text(f"Authorization: Bearer {token}; token={token}", [token])
    assert token not in result
    assert REDACTED in result
    assert redact_data({"token": token, "message": token}, [token]) == {"token": REDACTED, "message": REDACTED}


def test_empty_tokens_are_ignored_by_redaction() -> None:
    assert redact_text("status=ok", [""]) == "status=ok"
    assert redact_data({"message": "status=ok"}, [""]) == {"message": "status=ok"}


def test_pagination_cursor_keys_are_not_redacted() -> None:
    assert redact_data({"nextPageToken": "abc123"}) == {"nextPageToken": "abc123"}
    assert redact_data({"next_page_token": "abc123"}) == {"next_page_token": "abc123"}

    manifest = {
        "search-issues": {
            "response_schema": {
                "properties": {
                    "nextPageToken": {"type": "string", "description": "Cursor for the next page"},
                    "next_page_token": {"type": "string", "description": "Request field echoing the cursor"},
                }
            }
        }
    }
    assert redact_data(manifest) == manifest


def test_pagination_allowlist_does_not_widen_other_secret_redaction() -> None:
    payload = {
        "token": "very-secret-token",
        "api_key": "sk-super-secret",
        "authorization": "Bearer very-secret-token",
        "message": "Authorization: Bearer secret123",
    }
    assert redact_data(payload) == {
        "token": REDACTED,
        "api_key": REDACTED,
        "authorization": REDACTED,
        "message": f"Authorization: {REDACTED}",
    }
