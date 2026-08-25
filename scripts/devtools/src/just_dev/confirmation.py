"""Shared non-interactive-safe confirmation policy for mutations."""

from __future__ import annotations

import sys
from collections.abc import Callable

from .errors import ConfirmationError


def confirm_mutation(
    action: str,
    *,
    dry_run: bool = False,
    yes: bool = False,
    input_func: Callable[[str], str] = input,
    is_tty: bool | None = None,
) -> bool:
    """Return whether to execute a mutation; fail closed outside an interactive TTY."""

    if dry_run or yes:
        return False if dry_run else True
    interactive = sys.stdin.isatty() if is_tty is None else is_tty
    if not interactive:
        raise ConfirmationError(f"Refusing to {action} without --yes because stdin is not a TTY.")
    response = input_func(f"About to {action}. Continue? [y/N] ").strip().lower()
    if response not in {"y", "yes"}:
        raise ConfirmationError(f"Cancelled: {action}.")
    return True
