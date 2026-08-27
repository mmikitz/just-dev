"""End-to-end CLI validation paths surfaced by exploratory testing of the jira recipes.

These complement the existing workflow/operation unit tests: they exercise the same inputs through
the actual Typer `app`, so they also cover the option-parsing and exit-code plumbing those unit tests
don't reach (which Click/Typer layer rejects the value, and which `DevtoolsError.exit_code` comes back).
Assertions are kept to the invariant part of each message (the bad value, the allowed set) rather than
the full sentence, since exact wording is expected to keep improving independently of this contract.
"""

from __future__ import annotations

from typer.testing import CliRunner

from just_dev.cli import app
from just_dev.errors import InputValidationError

_CONFIG_TOML = """
[atlassian]
cloud_id = "00000000-0000-4000-8000-000000000123"
[jira.presets.bug]
project = "DEV"
issue_type = "Task"
[bitbucket]
workspace = "w"
repository = "r"
username = "u"
[jenkins]
url = "https://jenkins.example.test"
username = "u"
[confluence]
[project]
starter_hook = false
verify_commands = ["true"]
"""


def _config_path(tmp_path, monkeypatch):
    config_path = tmp_path / "project.toml"
    config_path.write_text(_CONFIG_TOML, encoding="utf-8")
    monkeypatch.setenv("JUST_DEV_PROJECT_ROOT", str(tmp_path))
    return config_path


def test_global_format_rejects_an_unknown_value_before_any_config_is_loaded(tmp_path, monkeypatch) -> None:
    # Deliberately no --config and no JUST_DEV_PROJECT_ROOT: the top-level --format check runs before
    # Runtime (and therefore config loading) is constructed, so this must fail without touching either.
    # Force typer's rich error rendering to plain text: under CI (GITHUB_ACTIONS=true) it forces ANSI
    # color on regardless of the captured stream being a real terminal, and its option highlighter
    # inserts escape codes inside "--format" (matching the trailing "-format" as a short option before
    # the full "--format" match), which breaks a plain substring check.
    monkeypatch.setenv("_TYPER_FORCE_DISABLE_TERMINAL", "1")
    result = CliRunner().invoke(app, ["--format", "xml", "jira", "read-jira-issue", "DEV-1"])

    assert result.exit_code == 2, result.output
    assert "--format" in result.output
    assert "xml" in result.output or "text" in result.output


def test_read_jira_issue_rejects_an_unknown_format_value_given_after_the_subcommand(tmp_path, monkeypatch) -> None:
    """This --format check runs before `_execute`'s DevtoolsError-to-exit-code wrapper is active, so only
    `main()`'s outer catch-all maps it to exit 25 in a real run; CliRunner bypasses `main()` and reports
    an uncaught exception as exit 1 instead. Assert on the raised exception itself, which is what both
    `main()` and `_execute` actually key off, rather than on CliRunner's own exit-code translation."""
    config_path = _config_path(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        app, ["--config", str(config_path), "jira", "read-jira-issue", "DEV-1", "--format", "xml"]
    )

    assert isinstance(result.exception, InputValidationError), result.output
    assert result.exception.exit_code == 25
    assert "--format" in str(result.exception)


def test_read_jira_issue_rejects_an_unknown_include_value(tmp_path, monkeypatch) -> None:
    config_path = _config_path(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        app, ["--config", str(config_path), "jira", "read-jira-issue", "DEV-1", "--include", "bogus"]
    )

    assert result.exit_code == 25, result.output
    assert "--include" in result.output
    assert "bogus" in result.output


def test_read_jira_issue_rejects_a_repeated_include_value(tmp_path, monkeypatch) -> None:
    config_path = _config_path(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        app, ["--config", str(config_path), "jira", "read-jira-issue", "DEV-1", "--include", "links,links"]
    )

    assert result.exit_code == 25, result.output
    assert "--include" in result.output


def test_read_jira_issue_rejects_an_unknown_view_value(tmp_path, monkeypatch) -> None:
    config_path = _config_path(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        app, ["--config", str(config_path), "jira", "read-jira-issue", "DEV-1", "--view", "bogus"]
    )

    assert result.exit_code == 25, result.output
    assert "--view" in result.output


def test_search_jira_issues_rejects_an_unknown_view_value(tmp_path, monkeypatch) -> None:
    config_path = _config_path(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        app, ["--config", str(config_path), "jira", "search-jira-issues", "project = DEV", "--view", "bogus"]
    )

    assert result.exit_code == 25, result.output
    assert "--view" in result.output


def test_search_jira_issues_rejects_an_out_of_range_limit(tmp_path, monkeypatch) -> None:
    config_path = _config_path(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        app, ["--config", str(config_path), "jira", "search-jira-issues", "project = DEV", "--limit", "0"]
    )

    assert result.exit_code == 25, result.output
    assert "--limit" in result.output


def test_comment_jira_issue_refuses_without_yes_when_stdin_is_not_a_tty(tmp_path, monkeypatch) -> None:
    config_path = _config_path(tmp_path, monkeypatch)

    result = CliRunner().invoke(app, ["--config", str(config_path), "jira", "comment-jira-issue", "DEV-1", "A comment"])

    assert result.exit_code == 26, result.output
    assert "--yes" in result.output


def test_attach_jira_issue_refuses_without_yes_when_stdin_is_not_a_tty(tmp_path, monkeypatch) -> None:
    config_path = _config_path(tmp_path, monkeypatch)
    attachment = tmp_path / "notes.txt"
    attachment.write_text("hello", encoding="utf-8")

    result = CliRunner().invoke(
        app, ["--config", str(config_path), "jira", "attach-jira-issue", "DEV-1", str(attachment)]
    )

    assert result.exit_code == 26, result.output
    assert "--yes" in result.output


def test_delete_jira_issue_refuses_without_yes_when_stdin_is_not_a_tty(tmp_path, monkeypatch) -> None:
    config_path = _config_path(tmp_path, monkeypatch)

    result = CliRunner().invoke(app, ["--config", str(config_path), "jira", "delete-jira-issue", "DEV-1"])

    assert result.exit_code == 26, result.output
    assert "--yes" in result.output
