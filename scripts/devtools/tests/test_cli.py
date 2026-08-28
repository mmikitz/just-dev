from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from just_dev.broker import KeePassProfile, ProfileStore
from just_dev.cli import Runtime, _CiOperationClient, _LazyBroker, app
from just_dev.errors import ConfigurationError, ConfirmationError, ConflictError, DevtoolsError
from just_dev.models import BrokerStatus, PreviewResult


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


def test_show_auth_status_reports_ci_tokens_instead_of_the_absent_local_broker(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("JUST_DEV_CI_JIRA_TOKEN", "ci-secret")
    for scope in ("CONFLUENCE", "BITBUCKET", "JENKINS"):
        monkeypatch.delenv(f"JUST_DEV_CI_{scope}_TOKEN", raising=False)

    result = CliRunner().invoke(app, ["--format", "json", "auth", "show-auth-status"])

    assert result.exit_code == 0, result.output
    assert '"active": true' in result.output
    assert '"source": "ci"' in result.output


def test_show_auth_status_reports_inactive_in_ci_with_no_tokens_configured(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    for scope in ("JIRA", "CONFLUENCE", "BITBUCKET", "JENKINS"):
        monkeypatch.delenv(f"JUST_DEV_CI_{scope}_TOKEN", raising=False)

    result = CliRunner().invoke(app, ["--format", "json", "auth", "show-auth-status"])

    assert result.exit_code == 0, result.output
    assert '"active": false' in result.output
    assert '"source": "ci"' in result.output
    # R4: nothing to probe when there is no active credential at all.
    assert '"verified": null' in result.output


class _FakeBrokerManager:
    """Stands in for BrokerManager() so show-auth-status's local-path `active` is
    controllable without a real KeePass database or broker subprocess."""

    def __init__(self, *, active: bool) -> None:
        self._active = active

    def status(self, profile: str) -> BrokerStatus:
        assert profile == "default"
        return BrokerStatus(active=self._active)


def _stub_local_profile_with_a_jira_entry(monkeypatch, tmp_path) -> None:
    store = ProfileStore(tmp_path / "profiles")
    store.save(
        "default",
        KeePassProfile(
            database=str(tmp_path / "secrets.kdbx"),
            entries={"jira": "00000000-0000-4000-8000-000000000099"},
        ),
    )
    monkeypatch.setattr("just_dev.cli.ProfileStore", lambda: store)


def test_show_auth_status_never_probes_when_the_broker_is_inactive(monkeypatch, tmp_path) -> None:
    """active=False -> verified stays None; there is no credential to test."""

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr("just_dev.cli.BrokerManager", lambda: _FakeBrokerManager(active=False))

    class FakeService:
        def verify_jira_credentials(self):
            raise AssertionError("the probe must not run when the broker is inactive")

    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: FakeService())

    result = CliRunner().invoke(app, ["--format", "json", "auth", "show-auth-status"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["active"] is False
    assert payload["verified"] is None


def test_show_auth_status_reports_verified_true_when_the_probe_succeeds(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr("just_dev.cli.BrokerManager", lambda: _FakeBrokerManager(active=True))
    _stub_local_profile_with_a_jira_entry(monkeypatch, tmp_path)

    class FakeService:
        def verify_jira_credentials(self):
            return True

    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: FakeService())

    result = CliRunner().invoke(app, ["--format", "json", "auth", "show-auth-status"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["active"] is True
    assert payload["verified"] is True


def test_show_auth_status_reports_verified_false_when_the_probe_confirms_a_bad_credential(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr("just_dev.cli.BrokerManager", lambda: _FakeBrokerManager(active=True))
    _stub_local_profile_with_a_jira_entry(monkeypatch, tmp_path)

    class FakeService:
        def verify_jira_credentials(self):
            return False

    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: FakeService())

    result = CliRunner().invoke(app, ["--format", "json", "auth", "show-auth-status"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["active"] is True
    assert payload["verified"] is False


def test_show_auth_status_reports_verified_none_when_no_jira_credential_is_configured(monkeypatch, tmp_path) -> None:
    """active=True only proves *some* scope was unlocked (R4): with no Jira entry in
    this profile at all, there is still nothing to probe, so verified stays None."""

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr("just_dev.cli.BrokerManager", lambda: _FakeBrokerManager(active=True))
    store = ProfileStore(tmp_path / "profiles")
    store.save(
        "default",
        KeePassProfile(
            database=str(tmp_path / "secrets.kdbx"), entries={"jenkins": "00000000-0000-4000-8000-000000000099"}
        ),
    )
    monkeypatch.setattr("just_dev.cli.ProfileStore", lambda: store)

    class FakeService:
        def verify_jira_credentials(self):
            raise AssertionError("the probe must not run without a configured Jira credential")

    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: FakeService())

    result = CliRunner().invoke(app, ["--format", "json", "auth", "show-auth-status"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["active"] is True
    assert payload["verified"] is None


def test_show_auth_status_reports_verified_none_when_the_probe_itself_cannot_run(monkeypatch, tmp_path) -> None:
    """active=True with a Jira credential configured, but the probe can't complete
    (e.g. an unresolvable Cloud ID): "couldn't check" must not read as "confirmed
    bad" (False) or "confirmed good" (True)."""

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr("just_dev.cli.BrokerManager", lambda: _FakeBrokerManager(active=True))
    _stub_local_profile_with_a_jira_entry(monkeypatch, tmp_path)

    class FakeService:
        def verify_jira_credentials(self):
            raise ConfigurationError("No Cloud ID is available for the configured Atlassian site.")

    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: FakeService())

    result = CliRunner().invoke(app, ["--format", "json", "auth", "show-auth-status"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["active"] is True
    assert payload["verified"] is None


def test_show_auth_status_reports_verified_none_in_ci_when_no_jira_token_is_configured(monkeypatch) -> None:
    """The CI-side twin of the "no Jira credential configured" case: some other
    scope's token being present is enough for active=True, but not enough to probe
    Jira specifically."""

    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("JUST_DEV_CI_JIRA_TOKEN", raising=False)
    monkeypatch.setenv("JUST_DEV_CI_BITBUCKET_TOKEN", "ci-secret")

    class FakeService:
        def verify_jira_credentials(self):
            raise AssertionError("the probe must not run without a configured CI Jira token")

    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: FakeService())

    result = CliRunner().invoke(app, ["--format", "json", "auth", "show-auth-status"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["active"] is True
    assert payload["verified"] is None


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


def test_transition_jira_issue_dry_run_still_checks_available_transitions(tmp_path, monkeypatch) -> None:
    """F2: --dry-run rehearses the transition lookup instead of skipping the broker
    entirely, so an unknown status or a nonexistent issue fails during dry-run too. That
    means this dry-run does need a broker call now (unlike e.g. create-jira-issue's) — so,
    following the same pattern as the _CiOperationClient tests above, fake the single
    read-only call it makes instead of reaching a real Jira site."""

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
[confluence]
[project]
starter_hook = false
verify_commands = ["true"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("JUST_DEV_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("JUST_DEV_CI_JIRA_TOKEN", "ci-secret")
    calls = []

    def fake_execute(tokens, operation, payload):
        calls.append(operation)
        return {"transitions": [{"id": "31", "to": {"name": "Done"}}]}

    monkeypatch.setattr("just_dev.cli.execute_operation", fake_execute)

    result = CliRunner().invoke(
        app,
        ["--config", str(config_path), "jira", "transition-jira-issue", "ABC-123", "Done", "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "transition Jira issue" in result.output
    assert calls == ["jira.list_transitions"]


def test_attach_jira_issue_dry_run_needs_no_broker(tmp_path, monkeypatch) -> None:
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
[confluence]
[project]
starter_hook = false
verify_commands = ["true"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("JUST_DEV_PROJECT_ROOT", str(tmp_path))
    attachment = tmp_path / "screenshot.png"
    attachment.write_bytes(b"fake image bytes")

    result = CliRunner().invoke(
        app,
        ["--config", str(config_path), "jira", "attach-jira-issue", "ABC-123", str(attachment), "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "attach file to Jira issue" in result.output
    assert "screenshot.png" in result.output


def test_merge_pull_request_dry_run_needs_no_broker(tmp_path, monkeypatch) -> None:
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
[confluence]
[project]
starter_hook = false
verify_commands = ["true"]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("JUST_DEV_PROJECT_ROOT", str(tmp_path))

    result = CliRunner().invoke(
        app,
        ["--config", str(config_path), "bitbucket", "merge-pull-request", "42", "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert "merge pull request" in result.output


def test_confirmed_mutation_puts_exactly_one_json_document_on_stdout(monkeypatch) -> None:
    """F1/F2: a confirmed (--yes) mutation's preview goes to stderr in the same
    bare shape --dry-run returns as its result, so --format json's stdout is
    exactly one parseable JSON document (principle 20), not two."""

    class FakeService:
        def create_jira_issue(self, preset, summary, **kwargs):
            announce = kwargs["announce"]
            announce(PreviewResult(action="create Jira issue", details={"preset": preset, "summary": summary}))
            return {"id": "10001", "key": "DEV-1"}

    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: FakeService())

    result = CliRunner().invoke(
        app,
        ["--format", "json", "jira", "create-jira-issue", "bug", "Summary", "--yes"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"id": "10001", "key": "DEV-1"}
    preview = json.loads(result.stderr)
    assert preview == {"action": "create Jira issue", "details": {"preset": "bug", "summary": "Summary"}}


def test_explicit_yes_wins_over_a_stale_just_dev_yes(monkeypatch) -> None:
    """principle 23: an explicit --yes on the command line needs no announcement,
    even with a stale JUST_DEV_YES also set in the environment."""

    class FakeService:
        def create_jira_issue(self, preset, summary, **kwargs):
            kwargs["announce"](PreviewResult(action="create Jira issue", details={}))
            return {"id": "10001", "key": "DEV-1"}

    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: FakeService())
    monkeypatch.setenv("JUST_DEV_YES", "1")

    result = CliRunner().invoke(app, ["jira", "create-jira-issue", "bug", "Summary", "--yes"])

    assert result.exit_code == 0, result.output
    assert "confirmation waived" not in result.stderr
    assert "JUST_DEV_YES" not in result.stderr


def test_just_dev_yes_environment_variable_no_longer_waives_confirmation(monkeypatch) -> None:
    """F6/principle 23: consent is argv-only now. JUST_DEV_YES alone no longer
    waives confirmation -- only an explicit --yes does -- and a lingering
    JUST_DEV_YES earns a warning while the mutation still fails closed exactly
    as an unconfirmed one always has (ConfirmationError, exit 26)."""

    class FakeService:
        def create_jira_issue(self, preset, summary, **kwargs):
            if not kwargs["yes"]:
                raise ConfirmationError("Refusing to create the Jira issue without --yes because stdin is not a TTY.")
            kwargs["announce"](PreviewResult(action="create Jira issue", details={}))
            return {"id": "10001", "key": "DEV-1"}

    monkeypatch.setattr(Runtime, "service", lambda self, profile="default", require_broker=True: FakeService())
    monkeypatch.setenv("JUST_DEV_YES", "1")

    result = CliRunner().invoke(app, ["jira", "create-jira-issue", "bug", "Summary"])

    assert result.exit_code == 26, result.output
    assert "warning: JUST_DEV_YES no longer waives confirmation; pass --yes" in result.stderr


def test_describe_commands_lists_every_command_as_an_mcp_shaped_tool(monkeypatch) -> None:
    result = CliRunner().invoke(app, ["--format", "json", "describe-commands"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    tools = {tool["name"]: tool for tool in payload["tools"]}
    assert "jira.read-jira-issue" in tools
    read_issue = tools["jira.read-jira-issue"]
    assert read_issue["annotations"] == {"readOnly": True, "destructive": False, "idempotent": True}
    assert "issue_id_or_key" in read_issue["inputSchema"]["properties"]
    assert read_issue["outputSchema"]["properties"]["fields"] == {"type": "object"}
    assert tools["jira.create-jira-issue"]["inputSchema"]["properties"]["extra_fields"]["type"] == "object"
    assert "fields" not in tools["jira.create-jira-issue"]["inputSchema"]["properties"]


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
    assert '"assignee": "[OMITTED]"' in safe_json.output
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
