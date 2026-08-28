"""Stable, redacted error categories for the command line interface."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CAMEL_WORD = re.compile(r"(?<!^)(?=[A-Z])")


@dataclass(eq=False)
class DevtoolsError(Exception):
    """An expected failure that has a documented process exit status."""

    message: str
    exit_code: int = 70
    # Set only by _sdk_error's generic-4xx branch (adapters.py), so a caller can narrowly
    # detect "this was an HTTP 404" without string-matching the message or a new `kind`.
    status_code: int | None = None

    @property
    def kind(self) -> str:
        """A stable, machine-readable failure category for `--format json` (F3)."""

        name = type(self).__name__.removesuffix("Error") or type(self).__name__
        return _CAMEL_WORD.sub("_", name).lower()

    def __str__(self) -> str:
        return self.message


class ConfigurationError(DevtoolsError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 20)


class AuthenticationError(DevtoolsError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 21)


class PermissionDeniedError(DevtoolsError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 22)


class ConflictError(DevtoolsError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 23)


class NetworkError(DevtoolsError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 24)


class InputValidationError(DevtoolsError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 25)


class ConfirmationError(DevtoolsError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 26)


class BrokerError(DevtoolsError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 27)


class VerificationError(DevtoolsError):
    def __init__(self, message: str) -> None:
        super().__init__(message, 28)
