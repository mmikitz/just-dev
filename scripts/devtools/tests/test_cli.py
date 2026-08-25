from __future__ import annotations

import pytest
from typer.testing import CliRunner

from just_dev.cli import _CiOperationClient, app
from just_dev.errors import ConflictError, DevtoolsError


def test_preview_release_notes_needs_no_broker(config, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "project.toml"
    config_path.write_text(
        """
[atlassian]
cloud_id = "cloud-123"
[jira]
[bitbucket]
workspace = "w"
repository = "r"
username = "u"
[jenkins]
url = "https://jenkins.example.test"
username = "u"
[confluence.presets.release-notes]
page_id = "42"
title = "Release notes"
[project]
starter_hook = false
verify_commands = ["true"]
""",
        encoding="utf-8",
    )
    notes = tmp_path / "notes.md"
    notes.write_text("# Notes", encoding="utf-8")
    monkeypatch.setenv("JUST_DEV_PROJECT_ROOT", str(tmp_path))

    result = CliRunner().invoke(
        app, ["--config", str(config_path), "--format", "json", "confluence", "preview-release-notes", str(notes)]
    )

    assert result.exit_code == 0, result.output
    assert '"page_id": "42"' in result.output
    assert "<h1>Notes</h1>" in result.output


def test_ci_operation_client_uses_process_injected_credentials_without_broker(monkeypatch) -> None:
    captured = {}

    def fake_execute(tokens, operation, payload):
        captured.update(tokens=tokens, operation=operation, payload=payload)
        return {"ok": True}

    monkeypatch.setattr("just_dev.cli.execute_operation", fake_execute)
    monkeypatch.setenv("JUST_DEV_CI_JENKINS_TOKEN", "ci-secret")

    assert _CiOperationClient().invoke("jenkins.run_build", {"preset": "test"}) == {"ok": True}
    assert captured["tokens"]["jenkins"] == "ci-secret"
    assert captured["operation"] == "jenkins.run_build"


def test_ci_operation_client_redacts_a_devtools_error_message(monkeypatch) -> None:
    def fake_execute(tokens, operation, payload):
        raise ConflictError(f"Remote echoed token={tokens['jenkins']} back")

    monkeypatch.setattr("just_dev.cli.execute_operation", fake_execute)
    monkeypatch.setenv("JUST_DEV_CI_JENKINS_TOKEN", "ci-secret")

    with pytest.raises(ConflictError) as raised:
        _CiOperationClient().invoke("jenkins.run_build", {"preset": "test"})

    assert "ci-secret" not in str(raised.value)


def test_ci_operation_client_redacts_an_unexpected_exception_instead_of_leaking_it(monkeypatch) -> None:
    def fake_execute(tokens, operation, payload):
        # Simulates a bug or an SDK exception type the adapter layer does not translate.
        raise KeyError(f"unexpected field near token={tokens['jenkins']}")

    monkeypatch.setattr("just_dev.cli.execute_operation", fake_execute)
    monkeypatch.setenv("JUST_DEV_CI_JENKINS_TOKEN", "ci-secret")

    with pytest.raises(DevtoolsError) as raised:
        _CiOperationClient().invoke("jenkins.run_build", {"preset": "test"})

    assert "ci-secret" not in str(raised.value)
    # `from None` suppresses the raw KeyError from ever being printed via exception chaining.
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True


def test_mutation_dry_run_needs_no_broker(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "project.toml"
    config_path.write_text(
        """
[atlassian]
cloud_id = "cloud-123"
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
[confluence.presets.release-notes]
page_id = "42"
title = "Release notes"
[project]
starter_hook = false
verify_commands = ["true"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("JUST_DEV_PROJECT_ROOT", str(tmp_path))

    result = CliRunner().invoke(
        app,
        [
            "--config",
            str(config_path),
            "jira",
            "create-jira-issue",
            "bug",
            "Dry run",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "create Jira issue" in result.output

    monkeypatch.setenv("JUST_DEV_JIRA_PRESET", "bug")
    monkeypatch.setenv("JUST_DEV_JIRA_SUMMARY", "From recipe")
    from_recipe = CliRunner().invoke(
        app,
        ["--config", str(config_path), "jira", "create-jira-issue", "--dry-run"],
    )

    assert from_recipe.exit_code == 0, from_recipe.output
    assert "From recipe" in from_recipe.output
