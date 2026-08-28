from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from just_dev.cli import app
from just_dev.introspect import describe_commands

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

# describe_commands(app) names each command "module.recipe" (bare "recipe" for the two commands
# registered directly on the top-level app, whose recipes nonetheless live in the "devtools"
# just module) -- derived from RECIPES so the mapping can't drift from the table above.
_RECIPE_BY_DOTTED_NAME: dict[str, tuple[str, str, tuple[str, ...]]] = {
    (recipe if module == "devtools" else f"{module}.{recipe}"): (module, recipe, args)
    for _alias, module, recipe, args, _env_vars, _argv_suffix in RECIPES
}

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


# F6/principle 23: --yes is never carried by an exported JUST_DEV_YES env var (unlike every
# other mutation flag) -- one recipe per module, translated back into a literal --yes argv
# entry by the recipe body's conditional interpolation.
@requires_just
@pytest.mark.parametrize(
    ("alias", "args"),
    [
        ("create-jira-issue", ("bug", "Summary")),
        ("merge-pull-request", ("42",)),
        ("run-build", ("release",)),
        ("publish-release-notes", ("notes.md",)),
    ],
    ids=["jira", "bitbucket", "jenkins", "confluence"],
)
def test_yes_flag_reaches_argv_and_never_the_environment(just_invocation, alias, args) -> None:
    with_yes = just_invocation(alias, *args, "--yes")
    without_yes = just_invocation(alias, *args)

    assert with_yes["argv"][-1] == "--yes"
    assert "JUST_DEV_YES" not in with_yes["env"]
    assert without_yes["argv"][-1] != "--yes"
    assert "JUST_DEV_YES" not in without_yes["env"]


@requires_just
def test_create_jira_issue_recipe_forwards_extra_fields_flag(just_invocation) -> None:
    captured = just_invocation("create-jira-issue", "bug", "Summary", "--extra-fields", '{"customfield_10010":"Prod"}')

    assert captured["env"]["JUST_DEV_JIRA_EXTRA_FIELDS"] == '{"customfield_10010":"Prod"}'


@requires_just
def test_create_jira_issue_rejects_the_old_fields_flag_name(just_invocation) -> None:
    completed = _run_just("create-jira-issue", "bug", "Summary", "--fields", '{"a":1}')

    assert completed.returncode != 0
    assert "does not have option" in completed.stderr
    assert "--fields" in completed.stderr


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


# --- Error paths: `just` itself rejects the two below before ever invoking `uv`/the Python CLI, so they
# need no fake-uv stub, no config, and no credentials -- they are pure option-name / eager-callback checks
# against the recipe signatures declared in recipes/jira.just. The missing-positional-arguments test right
# below `_run_just` is the one exception: it *does* reach the real Python CLI now (see its docstring). ---


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
    ("args", "message"),
    [
        (("transition-jira-issue",), "Issue ID or key is required."),
        (("transition-jira-issue", "DEV-1"), "Target status is required."),
        (("create-jira-issue",), "Jira preset is required."),
        (("comment-jira-issue", "DEV-1"), "Comment is required."),
        (("attach-jira-issue", "DEV-1"), "File path is required."),
    ],
    ids=["transition-zero-args", "transition-one-arg", "create-zero-args", "comment-one-arg", "attach-one-arg"],
)
def test_missing_positional_arguments_fail_python_side_validation(args, message) -> None:
    """U1: every recipe's leading positional now defaults to '' -- the accepted, intentional
    consequence of making `just <recipe> --help` reach Typer's own --help instead of dying in
    just's own parser (see the --help regression tests below). A call that omits a required
    positional no longer fails just's own argument-count usage error (exit 2); it reaches the
    Python CLI as an empty string, which `_argument_or_environment` (cli.py) rejects the same way
    it rejects any other missing required value: InputValidationError, exit 25."""

    completed = _run_just(*args)

    assert completed.returncode == 25
    assert f"error: {message}" in completed.stderr


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


# --- R1 regression gate: describe-commands must describe the recipe surface people actually
# invoke, in both directions -- every non-positional property is a real --kebab-flag `just`
# accepts and that carries its value through, and every x-cli-positional property is NOT also
# invocable as a flag, since it has none. ---


def _dummy_value(key: str, schema: dict) -> str:
    if key == "view":
        # The only recipe-level `[arg(..., pattern=...)]` constraint (jira.just's --view):
        # any other string would be rejected by `just` itself, before this test's flag even
        # gets a chance to matter.
        return "full"
    if schema.get("type") in ("integer", "number"):
        return "42"
    return f"dummy-{key}-value"


@requires_just
@pytest.mark.parametrize("tool", describe_commands(app), ids=lambda tool: str(tool["name"]))
def test_manifest_matches_the_real_recipe_surface(just_invocation, tool) -> None:
    """Before R1 this failed three separate ways: every command's `output_format` property
    published `--output-format`, which no recipe accepts (the real flag is `--format`);
    `issue_id_or_key` and `request` were published as ordinary properties even though they are
    positional and so have no `--flag` form at all; and `--profile` was missing from every
    jira/bitbucket/jenkins/confluence recipe even though every command already accepted it in
    Python. Walking describe_commands(app) rather than hand-listing commands/properties means a
    newly added command or parameter is covered automatically instead of silently joining a gap.
    """

    dotted_name = str(tool["name"])
    assert dotted_name in _RECIPE_BY_DOTTED_NAME, f"add {dotted_name} to RECIPES above so this test can drive it"
    module, recipe, required_args = _RECIPE_BY_DOTTED_NAME[dotted_name]

    for key, schema in tool["inputSchema"]["properties"].items():
        kebab_flag = "--" + key.replace("_", "-")

        if schema.get("x-cli-positional"):
            completed = _run_just(module, recipe, *required_args, kebab_flag, "dummy")
            assert completed.returncode != 0, (
                f"{dotted_name}: `just` accepted {kebab_flag}, but manifest property {key!r} is positional"
            )
            assert "does not have option" in completed.stderr, completed.stderr
            continue

        if schema.get("type") == "boolean":
            captured = just_invocation(module, recipe, *required_args, kebab_flag)
            landed = "1" in captured["env"].values() or kebab_flag in captured["argv"]
        else:
            value = _dummy_value(key, schema)
            captured = just_invocation(module, recipe, *required_args, kebab_flag, value)
            landed = value in captured["argv"] or value in captured["env"].values()
        assert landed, (
            f"{dotted_name}: `just` accepted {kebab_flag}, but its value never reached argv or a "
            f"JUST_DEV_* env var (manifest property {key!r})"
        )


# --- U1 regression gate: `just <recipe> --help` used to die in just's own parser -- "recipe
# 'x' does not have option '--help'" if HELP wasn't a declared `just` arg at all, or "got 0
# positional arguments but takes N" / usage: if a required positional came before it -- before
# the Python CLI (which already supports --help via Typer) ever ran. Every recipe with a
# required leading positional now defaults that positional to '' and declares a HELP arg
# threaded into argv the same way --yes is, so --help reaches argv with nothing else required. ---


@requires_just
@pytest.mark.parametrize(
    "alias",
    ["read-jira-issue", "create-pull-request", "run-build", "publish-release-notes", "unlock-secrets"],
    ids=["jira", "bitbucket", "jenkins", "confluence", "auth"],
)
def test_help_flag_reaches_argv_with_no_other_arguments(just_invocation, alias) -> None:
    """`just_invocation` itself asserts the underlying `just` call exits 0 (see its `run` helper),
    so a passing call here already proves just's parser accepted a bare `<recipe> --help` -- the
    remaining assertion confirms --help is exactly what reached the argv the real Python CLI (and
    therefore Typer's own --help output) would have received."""

    captured = just_invocation(alias, "--help")

    assert captured["argv"][-1] == "--help"


@requires_just
@pytest.mark.parametrize(
    "alias",
    ["read-jira-issue", "create-pull-request", "run-build", "publish-release-notes"],
    ids=["jira", "bitbucket", "jenkins", "confluence"],
)
def test_help_flag_prints_typer_help_and_exits_zero(alias) -> None:
    """The end-to-end counterpart to the argv-threading test above: runs the real Python CLI (no
    fake-uv stub) to confirm --help actually short-circuits to Typer's own help text at exit 0,
    not just that the flag survives `just`'s parser. Deliberately doesn't pin the exact program
    name Typer prints in the "Usage:" line or a specific options-panel heading -- those are
    cli.py's to choose and change; what U1 promises is that --help produces Typer's real,
    self-describing help output instead of dying in just's own parser."""

    completed = _run_just(alias, "--help")

    assert completed.returncode == 0, completed.stderr
    assert "Usage:" in completed.stdout
    assert "--help" in completed.stdout


# --- U5 regression gate: `just` takes the last comment line immediately above a recipe as its
# `just --list` description. A handful of recipes sat directly under an internal/maintainer-facing
# explanatory comment block (about $-prefixed parameters, --yes/F6/principle 23, the opt-in smoke
# test, or -- for describe-commands -- this very file), so `just --list` printed a fragment lifted
# from the middle of that block instead of a real description. Fixed with an explicit `[doc(...)]`
# attribute per recipe, confirmed by hand to win over the comment-derived description even with the
# explanatory block left in place directly above it. ---

_LIST_DESCRIPTION = re.compile(r"#\s+(.+)$", re.MULTILINE)


@requires_just
@pytest.mark.parametrize("module", ["jira", "bitbucket", "jenkins", "confluence", "auth", "devtools"])
def test_list_descriptions_read_as_real_sentences_not_comment_fragments(module) -> None:
    completed = _run_just("--list", module)
    assert completed.returncode == 0, completed.stderr

    descriptions = _LIST_DESCRIPTION.findall(completed.stdout)
    assert descriptions, f"expected at least one recipe description in `just --list {module}`"
    for description in descriptions:
        assert "OPEN_ISSUES.md" not in description, f"{description!r} leaks an internal doc reference"
        assert not description[:1].islower(), f"{description!r} reads like a sentence fragment, not a description"
