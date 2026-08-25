"""Unit tests for the `check-changed` pre-commit selection logic (recipes/check_changed.py).

Only `select_tests` is covered here: it is pure (no subprocess/git calls), unlike
`staged_files`/`main`, which are thin I/O wrappers exercised by actually running
`just check-changed` against a staged change (see the project's Lefthook hook).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "recipes" / "check_changed.py"
_spec = importlib.util.spec_from_file_location("check_changed", MODULE_PATH)
assert _spec and _spec.loader
check_changed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_changed)

SRC = check_changed.SRC
TESTS = check_changed.TESTS


def test_source_file_maps_to_its_matching_test_file() -> None:
    targets, full_suite = check_changed.select_tests([SRC / "broker.py"], [], [])

    assert targets == {TESTS / "test_broker.py"}
    assert full_suite is False


def test_two_source_files_sharing_one_test_file_deduplicate() -> None:
    targets, full_suite = check_changed.select_tests([SRC / "confirmation.py", SRC / "redaction.py"], [], [])

    assert targets == {TESTS / "test_confirmation_and_redaction.py"}
    assert full_suite is False


def test_source_file_without_a_matching_test_file_falls_back_to_the_full_suite() -> None:
    targets, full_suite = check_changed.select_tests([SRC / "models.py"], [], [])

    assert full_suite is True


def test_changed_conftest_always_falls_back_to_the_full_suite() -> None:
    targets, full_suite = check_changed.select_tests([], [TESTS / "conftest.py"], [])

    assert full_suite is True


def test_changed_test_file_is_run_directly() -> None:
    targets, full_suite = check_changed.select_tests([], [TESTS / "test_markdown.py"], [])

    assert targets == {TESTS / "test_markdown.py"}
    assert full_suite is False


def test_changed_justfile_adds_the_justfile_tests() -> None:
    targets, full_suite = check_changed.select_tests([], [], [SRC.parents[1] / "justfile"])

    assert targets == {TESTS / "test_justfiles.py"}
    assert full_suite is False


def test_nothing_changed_selects_nothing() -> None:
    assert check_changed.select_tests([], [], []) == (set(), False)
