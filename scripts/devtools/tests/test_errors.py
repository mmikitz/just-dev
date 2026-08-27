from __future__ import annotations

import pytest

from just_dev.errors import (
    AuthenticationError,
    BrokerError,
    ConfigurationError,
    ConfirmationError,
    ConflictError,
    DevtoolsError,
    InputValidationError,
    NetworkError,
    PermissionDeniedError,
    VerificationError,
)


@pytest.mark.parametrize(
    ("error_class", "exit_code", "kind"),
    [
        (ConfigurationError, 20, "configuration"),
        (AuthenticationError, 21, "authentication"),
        (PermissionDeniedError, 22, "permission_denied"),
        (ConflictError, 23, "conflict"),
        (NetworkError, 24, "network"),
        (InputValidationError, 25, "input_validation"),
        (ConfirmationError, 26, "confirmation"),
        (BrokerError, 27, "broker"),
        (VerificationError, 28, "verification"),
    ],
)
def test_kind_matches_the_readme_exit_code_table(error_class, exit_code, kind) -> None:
    error = error_class("message")

    assert error.exit_code == exit_code
    assert error.kind == kind


def test_devtools_error_falls_back_to_a_generic_kind() -> None:
    assert DevtoolsError("message").kind == "devtools"
