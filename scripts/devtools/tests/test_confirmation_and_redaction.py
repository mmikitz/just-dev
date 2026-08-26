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
