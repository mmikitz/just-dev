from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
REPO_ROOT = ROOT.parents[1]

# Every public alias and the module::recipe it must behave identically to (ARCHITECTURE.md's command table).
ALIASES = (
    "check-devtools",
    "describe-commands",
    "qa",
    "check-changed",
    "install-hooks",
    "configure-auth",
    "unlock-secrets",
    "show-auth-status",
    "lock-secrets",
    "create-jira-issue",
    "read-jira-issue",
    "search-jira-issues",
    "update-jira-issue",
    "assign-jira-issue",
    "comment-jira-issue",
    "attach-jira-issue",
    "transition-jira-issue",
    "delete-jira-issue",
    "jira-integration-smoke",
    "create-pull-request",
    "show-pull-request",
    "approve-pull-request",
    "decline-pull-request",
    "comment-pull-request",
    "add-pull-request-reviewer",
    "merge-pull-request",
    "run-build",
    "show-build-status",
    "preview-release-notes",
    "publish-release-notes",
    "verify-project",
    "run-ci",
)

# (alias, module, recipe, positional args to pass, JUST_DEV_* var each arg must land in, expected
# `just-dev` CLI argv, i.e. what the recipe body invokes after "uv run --locked just-dev").
RECIPES: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = (
    ("check-devtools", "devtools", "check-devtools", (), (), ("check-devtools",)),
    ("describe-commands", "devtools", "describe-commands", (), (), ("describe-commands",)),
    ("configure-auth", "auth", "configure-auth", (), (), ("auth", "configure-auth")),
    ("unlock-secrets", "auth", "unlock-secrets", (), (), ("auth", "unlock-secrets")),
    ("show-auth-status", "auth", "show-auth-status", (), (), ("auth", "show-auth-status")),
    ("lock-secrets", "auth", "lock-secrets", (), (), ("auth", "lock-secrets")),
    (
        "create-jira-issue",
        "jira",
        "create-jira-issue",
        ("bug", 'Fix: login & signup ($100 bug) "critical"'),
        ("JUST_DEV_JIRA_PRESET", "JUST_DEV_JIRA_SUMMARY"),
        ("jira", "create-jira-issue"),
    ),
    (
        "read-jira-issue",
        "jira",
        "read-jira-issue",
        ("ABC-123",),
        ("JUST_DEV_JIRA_ISSUE_ID_OR_KEY",),
        ("jira", "read-jira-issue"),
    ),
    (
        "search-jira-issues",
        "jira",
        "search-jira-issues",
        ("project = DEV",),
        ("JUST_DEV_JIRA_SEARCH_JQL",),
        ("jira", "search-jira-issues"),
    ),
    (
        "update-jira-issue",
        "jira",
        "update-jira-issue",
        ("ABC-123", '{"fields":{"customfield_10001":"new"},"notifyUsers":false,"returnIssue":true}'),
        ("JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "JUST_DEV_JIRA_UPDATE_REQUEST"),
        ("jira", "update-jira-issue"),
    ),
    (
        "assign-jira-issue",
        "jira",
        "assign-jira-issue",
        ("ABC-123",),
        ("JUST_DEV_JIRA_ISSUE_ID_OR_KEY",),
        ("jira", "assign-jira-issue"),
    ),
    (
        "comment-jira-issue",
        "jira",
        "comment-jira-issue",
        ("ABC-123", "Looks good to me"),
        ("JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "JUST_DEV_JIRA_COMMENT"),
        ("jira", "comment-jira-issue"),
    ),
    (
        "attach-jira-issue",
        "jira",
        "attach-jira-issue",
        ("ABC-123", "./screenshot.png"),
        ("JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "JUST_DEV_JIRA_FILE_PATH"),
        ("jira", "attach-jira-issue"),
    ),
    (
        "transition-jira-issue",
        "jira",
        "transition-jira-issue",
        ("ABC-123", "Done"),
        ("JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "JUST_DEV_JIRA_STATUS"),
        ("jira", "transition-jira-issue"),
    ),
    (
        "delete-jira-issue",
        "jira",
        "delete-jira-issue",
        ("ABC-123",),
        ("JUST_DEV_JIRA_ISSUE_ID_OR_KEY",),
        ("jira", "delete-jira-issue"),
    ),
    (
        "create-pull-request",
        "bitbucket",
        "create-pull-request",
        ("Add: caching layer (perf) & tests",),
        ("JUST_DEV_PR_TITLE",),
        ("bitbucket", "create-pull-request"),
    ),
    ("show-pull-request", "bitbucket", "show-pull-request", (), (), ("bitbucket", "show-pull-request")),
    (
        "approve-pull-request",
        "bitbucket",
        "approve-pull-request",
        ("42",),
        ("JUST_DEV_PR_ID",),
        ("bitbucket", "approve-pull-request"),
    ),
    (
        "decline-pull-request",
        "bitbucket",
        "decline-pull-request",
        ("42",),
        ("JUST_DEV_PR_ID",),
        ("bitbucket", "decline-pull-request"),
    ),
    (
        "comment-pull-request",
        "bitbucket",
        "comment-pull-request",
        ("42", "Looks good to me"),
        ("JUST_DEV_PR_ID", "JUST_DEV_PR_COMMENT"),
        ("bitbucket", "comment-pull-request"),
    ),
    (
        "add-pull-request-reviewer",
        "bitbucket",
        "add-pull-request-reviewer",
        ("42", "octocat"),
        ("JUST_DEV_PR_ID", "JUST_DEV_PR_REVIEWER_NAME"),
        ("bitbucket", "add-pull-request-reviewer"),
    ),
    (
        "merge-pull-request",
        "bitbucket",
        "merge-pull-request",
        ("42",),
        ("JUST_DEV_PR_ID",),
        ("bitbucket", "merge-pull-request"),
    ),
    (
        "run-build",
        "jenkins",
        "run-build",
        ("smoke-tests",),
        ("JUST_DEV_BUILD_PRESET",),
        ("jenkins", "run-build"),
    ),
    (
        "show-build-status",
        "jenkins",
        "show-build-status",
        ("smoke-tests", "42"),
        ("JUST_DEV_BUILD_PRESET", "JUST_DEV_BUILD_REFERENCE"),
        ("jenkins", "show-build-status"),
    ),
    (
        "preview-release-notes",
        "confluence",
        "preview-release-notes",
        ("release notes (v1) & fixes.md",),
        ("JUST_DEV_RELEASE_NOTES_FILE",),
        ("confluence", "preview-release-notes"),
    ),
    (
        "publish-release-notes",
        "confluence",
        "publish-release-notes",
        ("release notes (v1) & fixes.md",),
        ("JUST_DEV_RELEASE_NOTES_FILE",),
        ("confluence", "publish-release-notes"),
    ),
    ("verify-project", "project", "verify-project", (), (), ("project", "verify-project")),
    ("run-ci", "project", "run-ci", (), (), ("project", "run-ci")),
)

# A stand-in for `uv` that records how it was invoked instead of running the real CLI. This
# isolates the just-layer plumbing (recipe parameters -> exported JUST_DEV_* env vars -> command)
# from the Python CLI itself, which has its own test coverage.
_FAKE_UV_SOURCE = """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["JUST_DEV_TEST_CAPTURE_FILE"], "w", encoding="utf-8") as handle:
    json.dump(
        {
            "argv": sys.argv[1:],
            "env": {
                key: value
                for key, value in os.environ.items()
                if key.startswith("JUST_DEV_") and key != "JUST_DEV_TEST_CAPTURE_FILE"
            },
        },
        handle,
    )
"""

requires_just = pytest.mark.skipif(shutil.which("just") is None, reason="just is not installed")


def test_root_justfile_contains_only_portable_import() -> None:
    assert (REPO_ROOT / "justfile").read_text(encoding="utf-8") == "import 'scripts/devtools/justfile'\n"


def test_each_public_alias_has_its_namespaced_target() -> None:
    content = (ROOT / "justfile").read_text(encoding="utf-8")
    for alias in ALIASES:
        assert f"alias {alias} :=" in content


def test_jira_recipe_exposes_only_the_requested_targets() -> None:
    content = (ROOT / "recipes" / "jira.just").read_text(encoding="utf-8")
    targets = re.findall(r"^([a-z][a-z-]+)(?:\s+\$|:)", content, flags=re.MULTILINE)

    assert targets == [
        "create-jira-issue",
        "read-jira-issue",
        "search-jira-issues",
        "update-jira-issue",
        "assign-jira-issue",
        "comment-jira-issue",
        "attach-jira-issue",
        "transition-jira-issue",
        "delete-jira-issue",
        "jira-integration-smoke",
    ]


@pytest.fixture
def just_invocation(tmp_path):
    """Run a `just` recipe from the repo root with `uv` replaced by a capturing stub."""

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(_FAKE_UV_SOURCE, encoding="utf-8")
    fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    capture_file = tmp_path / "capture.json"

    def run(*args: str) -> dict:
        env = dict(os.environ)
        env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
        env["JUST_DEV_TEST_CAPTURE_FILE"] = str(capture_file)
        completed = subprocess.run(
            ["just", *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(capture_file.read_text(encoding="utf-8"))

    return run


@requires_just
@pytest.mark.parametrize(
    ("alias", "module", "recipe", "args", "env_vars", "argv_suffix"),
    RECIPES,
    ids=[entry[0] for entry in RECIPES],
)
def test_alias_and_namespace_form_run_the_same_recipe(
    just_invocation, alias, module, recipe, args, env_vars, argv_suffix
) -> None:
    via_alias = just_invocation(alias, *args)
    via_namespace = just_invocation(module, recipe, *args)

    assert via_alias == via_namespace
    assert via_alias["argv"] == ["run", "--locked", "just-dev", *argv_suffix]
    for env_var, value in zip(env_vars, args, strict=True):
        assert via_alias["env"][env_var] == value


@requires_just
def test_special_characters_and_spaces_survive_without_shell_interpolation(just_invocation) -> None:
    summary = 'Fix: login & signup ($100 bug) "critical"; rm -rf / #done'

    captured = just_invocation("create-jira-issue", "bug", summary)

    assert captured["env"]["JUST_DEV_JIRA_SUMMARY"] == summary


@requires_just
def test_configure_auth_recipe_forwards_incremental_and_repeated_options(just_invocation) -> None:
    database = "/tmp/credentials with spaces.kdbx"
    jira_entry = "00000000-0000-4000-8000-000000000001"
    confluence_entry = "00000000-0000-4000-8000-000000000002"
    arguments = (
        "--database",
        database,
        "--entry",
        f"jira={jira_entry}",
        "--entry",
        f"confluence={confluence_entry}",
        "--remove-entry",
        "jenkins",
        "--profile",
        "work",
    )

    captured = just_invocation("configure-auth", *arguments)

    assert captured["argv"] == ["run", "--locked", "just-dev", "auth", "configure-auth", *arguments]


@requires_just
def test_jira_read_recipe_forwards_view_include_and_output_flags(just_invocation) -> None:
    captured = just_invocation(
        "read-jira-issue",
        "ABC-123",
        "--fields",
        "summary,status",
        "--include",
        "comments,links",
        "--view",
        "full",
        "--format",
        "json",
        "--safe",
    )

    assert captured["env"]["JUST_DEV_JIRA_READ_FIELDS"] == "summary,status"
    assert captured["env"]["JUST_DEV_JIRA_READ_INCLUDE"] == "comments,links"
    assert captured["env"]["JUST_DEV_JIRA_READ_VIEW"] == "full"
    assert captured["env"]["JUST_DEV_FORMAT"] == "json"
    assert captured["env"]["JUST_DEV_SAFE"] == "1"


@requires_just
def test_jira_search_recipe_forwards_fields_view_limit_pagination_and_output_flags(just_invocation) -> None:
    captured = just_invocation(
        "search-jira-issues",
        "project = DEV",
        "--fields",
        "summary,status",
        "--view",
        "full",
        "--limit",
        "20",
        "--next-page-token",
        "CAEaAggD",
        "--expand",
        "names",
        "--format",
        "json",
        "--safe",
    )

    assert captured["env"]["JUST_DEV_JIRA_SEARCH_JQL"] == "project = DEV"
    assert captured["env"]["JUST_DEV_JIRA_SEARCH_FIELDS"] == "summary,status"
    assert captured["env"]["JUST_DEV_JIRA_SEARCH_VIEW"] == "full"
    assert captured["env"]["JUST_DEV_JIRA_SEARCH_LIMIT"] == "20"
    assert captured["env"]["JUST_DEV_JIRA_SEARCH_NEXT_PAGE_TOKEN"] == "CAEaAggD"
    assert captured["env"]["JUST_DEV_JIRA_SEARCH_EXPAND"] == "names"
    assert captured["env"]["JUST_DEV_FORMAT"] == "json"
    assert captured["env"]["JUST_DEV_SAFE"] == "1"


@requires_just
def test_assign_jira_issue_recipe_forwards_assignee_flag(just_invocation) -> None:
    captured = just_invocation("assign-jira-issue", "ABC-123", "--assignee", "abc123def456")

    assert captured["env"]["JUST_DEV_JIRA_ASSIGNEE"] == "abc123def456"


@requires_just
def test_update_jira_issue_recipe_forwards_labels_and_priority_flags(just_invocation) -> None:
    captured = just_invocation("update-jira-issue", "ABC-123", "--labels", "bug,urgent", "--priority", "High")

    assert captured["env"]["JUST_DEV_JIRA_LABELS"] == "bug,urgent"
    assert captured["env"]["JUST_DEV_JIRA_PRIORITY"] == "High"


@requires_just
def test_create_pull_request_recipe_forwards_description_reviewer_and_close_source_branch_flags(
    just_invocation,
) -> None:
    captured = just_invocation(
        "create-pull-request",
        "Add: caching layer",
        "--description",
        "Adds an in-memory cache in front of the slow lookup.",
        "--reviewer",
        "octocat",
        "--close-source-branch",
    )

    assert captured["env"]["JUST_DEV_PR_DESCRIPTION"] == "Adds an in-memory cache in front of the slow lookup."
    assert captured["env"]["JUST_DEV_PR_REVIEWER"] == "octocat"
    assert captured["env"]["JUST_DEV_PR_CLOSE_SOURCE_BRANCH"] == "1"


@requires_just
def test_merge_pull_request_recipe_forwards_message_and_merge_strategy_flags(just_invocation) -> None:
    captured = just_invocation(
        "merge-pull-request", "42", "--message", "Merging after review", "--merge-strategy", "squash"
    )

    assert captured["env"]["JUST_DEV_PR_MESSAGE"] == "Merging after review"
    assert captured["env"]["JUST_DEV_PR_MERGE_STRATEGY"] == "squash"


# --- Error paths: `just` itself rejects these before ever invoking `uv`/the Python CLI, so they need no
# fake-uv stub, no config, and no credentials -- they are pure argument-count / option-name checks against
# the recipe signatures declared in recipes/jira.just. ---


def _run_just(*args: str) -> subprocess.CompletedProcess:
    # Force typer's rich error rendering to plain text in the subprocess: under CI (GITHUB_ACTIONS=true)
    # it forces ANSI color on regardless of stderr being a real terminal, and its option highlighter can
    # split a long option like "--format" across escape codes, breaking plain substring assertions below.
    env = {**os.environ, "_TYPER_FORCE_DISABLE_TERMINAL": "1"}
    return subprocess.run(
        ["just", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


@requires_just
@pytest.mark.parametrize(
    ("args", "takes"),
    [
        (("transition-jira-issue",), 2),
        (("transition-jira-issue", "DEV-1"), 2),
        (("create-jira-issue",), 2),
        (("comment-jira-issue", "DEV-1"), 2),
        (("attach-jira-issue", "DEV-1"), 2),
    ],
    ids=["transition-zero-args", "transition-one-arg", "create-zero-args", "comment-one-arg", "attach-one-arg"],
)
def test_missing_positional_arguments_produce_justs_own_usage_error(args, takes) -> None:
    completed = _run_just(*args)

    assert completed.returncode != 0
    assert f"but takes {takes}" in completed.stderr
    assert "usage:" in completed.stderr


@requires_just
def test_unknown_flag_is_rejected_by_just_before_python_runs() -> None:
    completed = _run_just("read-jira-issue", "DEV-1", "--frobnicate", "value")

    assert completed.returncode != 0
    assert "does not have option" in completed.stderr
    assert "--frobnicate" in completed.stderr


@requires_just
def test_invalid_format_recipe_flag_surfaces_the_global_click_error_with_exit_code_two(tmp_path) -> None:
    """--format is forwarded as JUST_DEV_FORMAT and only validated by the top-level Typer callback, so
    an invalid value here fails before config is loaded and exits 2 (a Click usage error), not the 25
    (InputValidationError) a per-command validation failure would use."""
    completed = _run_just("read-jira-issue", "DEV-1", "--format", "xml")

    assert completed.returncode != 0
    assert "exit code 2" in completed.stderr
    assert "--format" in completed.stderr
