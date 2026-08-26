from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from just_dev.broker import KeePassProfile, ProfileStore
from just_dev.cli import Runtime, _CiOperationClient, _LazyBroker, app
from just_dev.errors import ConflictError, DevtoolsError


def test_preview_release_notes_needs_no_broker(config, tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "project.toml"
    config_path.write_text(
        """
[atlassian]
cloud_id = "00000000-0000-4000-8000-000000000123"
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


def test_runtime_service_selects_broker_from_the_ci_environment_variable(config, monkeypatch) -> None:
    monkeypatch.setattr("just_dev.cli.load_project_config", lambda *args, **kwargs: config)
    runtime = Runtime(config_path=None, output_format="text", project_root=Path("."))

    monkeypatch.delenv("CI", raising=False)
    assert isinstance(runtime.service("default").broker, _LazyBroker)

    monkeypatch.setenv("CI", "true")
    assert isinstance(runtime.service("default").broker, _CiOperationClient)

    monkeypatch.setenv("CI", "false")
    assert isinstance(runtime.service("default").broker, _LazyBroker)


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


def test_jira_read_defaults_to_markdown_and_applies_view_and_safe_output(monkeypatch) -> None:
    class FakeService:
        def __init__(self) -> None:
            self.arguments = None

        def read_jira_issue(self, issue, **kwargs):
            self.arguments = (issue, kwargs)
            return {
                "id": "10001",
                "key": issue,
                "self": "https://example.atlassian.net/issue/10001",
                "fields": {
                    "summary": "Readable issue",
                    "status": {"name": "Open"},
                    "assignee": {"displayName": "Ada", "accountId": "account-1"},
                    "description": "Free text is retained.",
                },
            }

    service = FakeService()
    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: service)

    markdown = CliRunner().invoke(
        app,
        ["jira", "read-jira-issue", "DEV-1", "--fields", "summary,status,assignee,description"],
    )
    safe_json = CliRunner().invoke(
        app,
        [
            "jira",
            "read-jira-issue",
            "DEV-1",
            "--fields",
            "summary,status,assignee,description",
            "--view",
            "full",
            "--format",
            "json",
            "--safe",
        ],
    )

    assert markdown.exit_code == 0, markdown.output
    assert markdown.output.startswith("# DEV-1: Readable issue")
    assert service.arguments == (
        "DEV-1",
        {
            "fields": "summary,status,assignee,description",
            "include": (),
            "view": "full",
            "expand": None,
            "properties": None,
        },
    )
    assert safe_json.exit_code == 0, safe_json.output
    assert "account-1" not in safe_json.output
    assert "assignee" not in safe_json.output
    assert "https://" not in safe_json.output


def test_configure_auth_updates_an_existing_profile_incrementally(tmp_path, monkeypatch) -> None:
    database = tmp_path / "credentials.kdbx"
    keyfile = tmp_path / "credentials.key"
    database.touch()
    keyfile.touch()
    store = ProfileStore(tmp_path / "profiles")
    jira_uuid = "00000000-0000-4000-8000-000000000001"
    jenkins_uuid = "00000000-0000-4000-8000-000000000002"
    confluence_uuid = "00000000-0000-4000-8000-000000000003"
    store.save(
        "work",
        KeePassProfile(
            database=str(database),
            keyfile=str(keyfile),
            entries={"jira": jira_uuid, "jenkins": jenkins_uuid},
        ),
    )
    monkeypatch.setattr("just_dev.cli.ProfileStore", lambda: store)
    monkeypatch.setattr(Runtime, "resolve_local_cloud_id", lambda *args, **kwargs: None)

    result = CliRunner().invoke(
        app,
        [
            "auth",
            "configure-auth",
            "--profile",
            "work",
            "--entry",
            f"confluence={confluence_uuid}",
            "--remove-entry",
            "jenkins",
            "--clear-keyfile",
        ],
    )

    assert result.exit_code == 0, result.output
    updated = store.load("work")
    assert updated.database == str(database)
    assert updated.keyfile is None
    assert updated.entries == {"jira": jira_uuid, "confluence": confluence_uuid}
