from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from just_dev.errors import ConfigurationError, InputValidationError
from just_dev.models import BuildResult, PageResult, PreviewResult, PullRequestResult
from just_dev.workflows import DevtoolsService


@dataclass
class FakeBroker:
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def invoke(self, operation: str, payload: dict) -> dict:
        self.calls.append((operation, payload))
        if operation == "jira.create_issue":
            return {"key": "DEV-1", "id": "10001", "self": "https://jira/DEV-1"}
        if operation == "jira.read_issue":
            return {"key": payload["issue_id_or_key"], "fields": {"summary": "Existing"}}
        if operation == "jira.update_issue":
            return {"issue_id_or_key": payload["issue_id_or_key"], "updated": True}
        if operation == "jira.delete_issue":
            return {"issue_id_or_key": payload["issue_id_or_key"], "deleted": True}
        if operation == "bitbucket.create_pull_request":
            return {
                "id": 7,
                "title": payload["title"],
                "source_branch": payload["source_branch"],
                "target_branch": "main",
            }
        if operation == "jenkins.run_build":
            return {"preset": payload["preset"], "queue_id": 9, "status": "queued"}
        if operation == "confluence.get_page":
            return {"page_id": "42", "title": "Release notes", "version": 3}
        if operation == "confluence.update_page":
            return {"page_id": "42", "title": "Release notes", "version": 4}
        raise AssertionError(f"Unexpected operation: {operation}")


class FakeVerification:
    def __init__(self) -> None:
        self.ran = False

    def run(self):
        self.ran = True
        return []


def test_dry_run_never_calls_broker(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    result = service.create_jira_issue("bug", "Safe preview", dry_run=True)

    assert isinstance(result, PreviewResult)
    assert broker.calls == []


def test_create_jira_issue_announces_preview_before_confirming(config, tmp_path) -> None:
    broker = FakeBroker()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker)

    result = service.create_jira_issue("bug", "Safe summary", yes=True, announce=announced.append)

    assert result["key"] == "DEV-1"
    assert announced == [PreviewResult(action="create Jira issue", details=announced[0].details)]
    assert announced[0].details["preset"] == "bug"
    assert announced[0].details["summary"] == "Safe summary"
    assert [name for name, _ in broker.calls] == ["jira.create_issue"]


def test_create_jira_issue_rejects_an_unknown_preset(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(ConfigurationError):
        service.create_jira_issue("missing", "Summary")


def test_create_jira_issue_rejects_preset_managed_fields(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.create_jira_issue("bug", "Summary", fields={"project": {"key": "OTHER"}})


def test_jira_read_update_and_delete_forward_all_request_values(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    read = service.read_jira_issue("DEV-1", fields="summary,customfield_10001", expand="names")
    updated = service.update_jira_issue(
        "DEV-1",
        summary="Updated summary",
        fields={"customfield_10001": "value"},
        yes=True,
    )
    deleted = service.delete_jira_issue("DEV-1", delete_subtasks=True, yes=True)

    assert read["fields"]["summary"] == "Existing"
    assert updated["updated"] is True
    assert deleted["deleted"] is True
    assert broker.calls[0][0] == "jira.read_issue"
    assert broker.calls[0][1]["parameters"] == {"fields": "summary,customfield_10001", "expand": "names"}
    assert broker.calls[1][1]["summary"] == "Updated summary"
    assert broker.calls[1][1]["request"] == {"customfield_10001": "value"}
    assert broker.calls[2][1]["parameters"] == {"deleteSubtasks": True}


def test_jira_operation_uses_the_runtime_resolved_cloud_id_in_broker_payload(config, tmp_path) -> None:
    broker = FakeBroker()
    site_config = config.model_copy(
        update={"atlassian": config.atlassian.model_copy(update={"cloud_id": "https://example.atlassian.net"})}
    )
    service = DevtoolsService(
        site_config,
        tmp_path,
        broker,
        cloud_id_resolver=lambda configured: "00000000-0000-4000-8000-000000000456",
    )

    service.read_jira_issue("DEV-1", fields="summary")

    assert broker.calls[0][1]["config"]["atlassian"]["cloud_id"] == "00000000-0000-4000-8000-000000000456"


def test_update_jira_issue_requires_something_to_change(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.update_jira_issue("DEV-1")


def test_pull_request_verifies_before_broker_operation(config, tmp_path) -> None:
    broker = FakeBroker()
    verification = FakeVerification()
    service = DevtoolsService(config, tmp_path, broker, verification_runner=verification)

    result = service.create_pull_request("A PR", source_branch="feature/x", yes=True)

    assert verification.ran is True
    assert result.id == 7
    assert broker.calls[0][0] == "bitbucket.create_pull_request"


def test_no_verify_is_explicit_and_does_not_run_verification(config, tmp_path) -> None:
    broker = FakeBroker()
    verification = FakeVerification()
    service = DevtoolsService(config, tmp_path, broker, verification_runner=verification)

    service.create_pull_request("A PR", source_branch="feature/x", no_verify=True, yes=True)

    assert verification.ran is False


def test_create_pull_request_announces_preview_before_confirming(config, tmp_path) -> None:
    broker = FakeBroker()
    verification = FakeVerification()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker, verification_runner=verification)

    result = service.create_pull_request("A PR", source_branch="feature/x", yes=True, announce=announced.append)

    assert isinstance(result, PullRequestResult)
    assert announced[0].details["title"] == "A PR"
    assert announced[0].details["source_branch"] == "feature/x"


def test_run_build_queues_named_preset(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    result = service.run_build("test", parameters=["REF=main"], yes=True)

    assert isinstance(result, BuildResult)
    assert broker.calls[0] == ("jenkins.run_build", broker.calls[0][1])


def test_run_build_announces_preview_before_confirming(config, tmp_path) -> None:
    broker = FakeBroker()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker)

    result = service.run_build("test", parameters=["REF=main"], yes=True, announce=announced.append)

    assert isinstance(result, BuildResult)
    assert announced[0].details["preset"] == "test"
    assert announced[0].details["parameters"] == {"REF": "main"}


def test_publish_previews_then_uses_versioned_broker_operation(config, tmp_path) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("# Release\n\nSafe text", encoding="utf-8")
    broker = FakeBroker()
    announced: list[PageResult] = []
    service = DevtoolsService(config, tmp_path, broker)

    result = service.publish_release_notes(notes, yes=True, announce=announced.append)

    assert result.version == 4
    assert announced[0].version == 3
    assert [name for name, _ in broker.calls] == ["confluence.get_page", "confluence.update_page"]
