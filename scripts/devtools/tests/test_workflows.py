from __future__ import annotations

import base64
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
        if operation == "jira.search_issues":
            return {"issues": [{"key": "DEV-1", "fields": {"summary": "Existing"}}], "isLast": True}
        if operation == "jira.update_issue":
            return {"issue_id_or_key": payload["issue_id_or_key"], "updated": True}
        if operation == "jira.delete_issue":
            return {"issue_id_or_key": payload["issue_id_or_key"], "deleted": True}
        if operation == "jira.assign_issue":
            return {"issue_id_or_key": payload["issue_id_or_key"], "assignee": payload["assignee"]}
        if operation == "jira.comment_issue":
            return {"id": "10050", "issue_id_or_key": payload["issue_id_or_key"]}
        if operation == "jira.attach_file":
            return {"issue_id_or_key": payload["issue_id_or_key"], "filename": payload["filename"]}
        if operation == "jira.list_transitions":
            return {
                "transitions": [
                    {"id": "11", "name": "Start Progress", "to": {"id": "3", "name": "In Progress"}},
                    {"id": "31", "name": "Done", "to": {"id": "10001", "name": "Done"}},
                ]
            }
        if operation == "jira.transition_issue":
            return {"issue_id_or_key": payload["issue_id_or_key"], "transitioned": True}
        if operation == "bitbucket.create_pull_request":
            return {
                "id": 7,
                "title": payload["title"],
                "source_branch": payload["source_branch"],
                "target_branch": "main",
            }
        if operation == "bitbucket.approve_pull_request":
            return {"pull_request_id": payload["pull_request_id"], "approved": True}
        if operation == "bitbucket.decline_pull_request":
            return {"pull_request_id": payload["pull_request_id"], "declined": True}
        if operation == "bitbucket.add_pull_request_comment":
            return {"id": 3, "pull_request_id": payload["pull_request_id"]}
        if operation == "bitbucket.add_pull_request_reviewer":
            return {"pull_request_id": payload["pull_request_id"], "reviewer": payload["reviewer"]}
        if operation == "bitbucket.merge_pull_request":
            return {"pull_request_id": payload["pull_request_id"], "merged": True, "message": payload["message"]}
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


def test_search_jira_issues_forwards_jql_fields_view_limit_and_pagination(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    result = service.search_jira_issues(
        "project = DEV",
        fields="summary,status",
        view="full",
        limit=25,
        next_page_token="CAEaAggD",
        expand="names",
    )

    assert result["issues"][0]["key"] == "DEV-1"
    assert broker.calls[0][0] == "jira.search_issues"
    assert broker.calls[0][1]["parameters"] == {
        "jql": "project = DEV",
        "fields": "summary,status",
        "maxResults": 25,
        "nextPageToken": "CAEaAggD",
        "expand": "names",
    }


def test_search_jira_issues_full_view_without_explicit_fields_requests_all_fields(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    service.search_jira_issues("project = DEV", view="full")

    # search/jql (unlike the single-issue read endpoint) returns no fields at
    # all when the parameter is omitted, so a full view must ask explicitly.
    assert broker.calls[0][1]["parameters"]["fields"] == "*all"


def test_search_jira_issues_summary_view_without_explicit_fields_uses_the_compact_default(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    service.search_jira_issues("project = DEV")

    assert broker.calls[0][1]["parameters"]["fields"] == "summary,status,assignee,reporter,issuetype,priority"


def test_search_jira_issues_rejects_an_empty_jql(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.search_jira_issues("   ")

    assert broker.calls == []


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_search_jira_issues_rejects_an_out_of_range_limit(config, tmp_path, limit) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.search_jira_issues("project = DEV", limit=limit)

    assert broker.calls == []


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


def test_update_jira_issue_accepts_labels_alone(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    service.update_jira_issue("DEV-1", labels="a,b", yes=True)

    assert broker.calls[0][1]["labels"] == "a,b"


def test_update_jira_issue_accepts_priority_alone(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    service.update_jira_issue("DEV-1", priority="High", yes=True)

    assert broker.calls[0][1]["priority"] == "High"


def test_update_jira_issue_rejects_a_field_set_by_both_the_json_body_and_a_flag(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError, match="summary"):
        service.update_jira_issue(
            "DEV-1",
            summary="from flag",
            fields={"fields": {"summary": "from json"}},
            yes=True,
        )

    assert broker.calls == []


def test_update_jira_issue_allows_the_json_body_and_flags_to_set_different_fields(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    service.update_jira_issue(
        "DEV-1",
        summary="from flag",
        fields={"fields": {"description": "from json"}},
        yes=True,
    )

    assert broker.calls[0][1]["summary"] == "from flag"
    assert broker.calls[0][1]["request"] == {"fields": {"description": "from json"}}


@pytest.mark.parametrize("issue_id_or_key", ["not a valid key!!", "-123", "ABC-"])
def test_jira_commands_reject_a_malformed_issue_key_before_calling_the_broker(
    config, tmp_path, issue_id_or_key
) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.read_jira_issue(issue_id_or_key)

    assert broker.calls == []


def test_assign_jira_issue_announces_preview_before_confirming(config, tmp_path) -> None:
    broker = FakeBroker()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker)

    result = service.assign_jira_issue("DEV-1", "abc123", yes=True, announce=announced.append)

    assert result["assignee"] == "abc123"
    assert announced[0].details["issue_id_or_key"] == "DEV-1"
    assert announced[0].details["assignee"] == "abc123"
    assert broker.calls[0][0] == "jira.assign_issue"


def test_assign_jira_issue_rejects_empty_assignee(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.assign_jira_issue("DEV-1", "   ")

    assert broker.calls == []


def test_assign_jira_issue_dry_run_never_calls_broker(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    result = service.assign_jira_issue("DEV-1", "abc123", dry_run=True)

    assert isinstance(result, PreviewResult)
    assert broker.calls == []


def test_comment_jira_issue_forwards_comment_text(config, tmp_path) -> None:
    broker = FakeBroker()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker)

    result = service.comment_jira_issue("DEV-1", "Looks good", yes=True, announce=announced.append)

    assert result["issue_id_or_key"] == "DEV-1"
    assert announced[0].details["comment"] == "Looks good"
    assert broker.calls[0] == ("jira.comment_issue", broker.calls[0][1])
    assert broker.calls[0][1]["comment"] == "Looks good"


def test_comment_jira_issue_rejects_empty_comment(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.comment_jira_issue("DEV-1", "  ")

    assert broker.calls == []


def test_attach_jira_issue_forwards_file_contents_as_base64(config, tmp_path) -> None:
    broker = FakeBroker()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker)
    file_path = tmp_path / "notes.txt"
    file_path.write_bytes(b"hello world")

    result = service.attach_jira_issue("DEV-1", str(file_path), yes=True, announce=announced.append)

    assert result["issue_id_or_key"] == "DEV-1"
    assert announced[0].details["filename"] == "notes.txt"
    assert announced[0].details["size_bytes"] == 11
    assert broker.calls[0][0] == "jira.attach_file"
    assert broker.calls[0][1]["filename"] == "notes.txt"
    assert base64.b64decode(broker.calls[0][1]["content_b64"]) == b"hello world"


def test_attach_jira_issue_rejects_a_missing_file(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.attach_jira_issue("DEV-1", str(tmp_path / "does-not-exist.txt"))

    assert broker.calls == []


def test_attach_jira_issue_rejects_a_file_over_the_size_limit(config, tmp_path, monkeypatch) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)
    monkeypatch.setattr(DevtoolsService, "_JIRA_MAX_ATTACHMENT_BYTES", 4)
    file_path = tmp_path / "big.bin"
    file_path.write_bytes(b"too big")

    with pytest.raises(InputValidationError):
        service.attach_jira_issue("DEV-1", str(file_path))

    assert broker.calls == []


def test_attach_jira_issue_dry_run_short_circuits_before_reading_the_file(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)
    file_path = tmp_path / "notes.txt"
    file_path.write_bytes(b"hello world")

    result = service.attach_jira_issue("DEV-1", str(file_path), dry_run=True)

    assert isinstance(result, PreviewResult)
    assert result.details["filename"] == "notes.txt"
    assert "content_b64" not in result.details
    assert broker.calls == []


def test_transition_jira_issue_dry_run_never_calls_broker(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    result = service.transition_jira_issue("DEV-1", "Done", dry_run=True)

    assert isinstance(result, PreviewResult)
    assert result.details["status"] == "Done"
    assert broker.calls == []


def test_transition_jira_issue_resolves_status_to_transition_id_case_insensitively(config, tmp_path) -> None:
    broker = FakeBroker()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker)

    result = service.transition_jira_issue("DEV-1", "in progress", yes=True, announce=announced.append)

    assert result["transitioned"] is True
    assert [name for name, _ in broker.calls] == ["jira.list_transitions", "jira.transition_issue"]
    assert broker.calls[1][1]["transition_id"] == "11"
    assert announced[0].details["status"] == "In Progress"
    assert announced[0].details["transition_id"] == "11"


def test_transition_jira_issue_rejects_unknown_status_with_allowed_list(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(
        InputValidationError, match=r"Unknown status 'Bogus'\. Allowed transitions: In Progress, Done\."
    ):
        service.transition_jira_issue("DEV-1", "Bogus")

    assert [name for name, _ in broker.calls] == ["jira.list_transitions"]


def test_transition_jira_issue_rejects_empty_status(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.transition_jira_issue("DEV-1", "   ")

    assert broker.calls == []


def test_approve_pull_request_dry_run_never_calls_broker(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    result = service.approve_pull_request("42", dry_run=True)

    assert isinstance(result, PreviewResult)
    assert broker.calls == []


def test_approve_pull_request_announces_preview_before_confirming(config, tmp_path) -> None:
    broker = FakeBroker()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker)

    result = service.approve_pull_request("42", yes=True, announce=announced.append)

    assert result["approved"] is True
    assert announced[0].details["pull_request_id"] == "42"
    assert broker.calls[0][0] == "bitbucket.approve_pull_request"


def test_approve_pull_request_rejects_empty_id(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.approve_pull_request("  ")

    assert broker.calls == []


def test_decline_pull_request_invokes_broker(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    result = service.decline_pull_request("42", yes=True)

    assert result["declined"] is True
    assert broker.calls[0][0] == "bitbucket.decline_pull_request"


def test_comment_pull_request_forwards_comment_text(config, tmp_path) -> None:
    broker = FakeBroker()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker)

    result = service.comment_pull_request("42", "lgtm", yes=True, announce=announced.append)

    assert result["pull_request_id"] == "42"
    assert announced[0].details["comment"] == "lgtm"
    assert broker.calls[0][1]["comment"] == "lgtm"


def test_comment_pull_request_rejects_empty_comment(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.comment_pull_request("42", "   ")

    assert broker.calls == []


def test_add_pull_request_reviewer_forwards_reviewer(config, tmp_path) -> None:
    broker = FakeBroker()
    announced: list[PreviewResult] = []
    service = DevtoolsService(config, tmp_path, broker)

    result = service.add_pull_request_reviewer("42", "alice", yes=True, announce=announced.append)

    assert result["reviewer"] == "alice"
    assert announced[0].details["reviewer"] == "alice"
    assert broker.calls[0][0] == "bitbucket.add_pull_request_reviewer"


def test_add_pull_request_reviewer_rejects_empty_reviewer(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(InputValidationError):
        service.add_pull_request_reviewer("42", "  ")

    assert broker.calls == []


def test_merge_pull_request_synthesizes_default_message_when_omitted(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    result = service.merge_pull_request("42", yes=True)

    assert result["message"] == "Merge pull request #42"
    assert broker.calls[0][1]["message"] == "Merge pull request #42"
    assert broker.calls[0][1]["merge_strategy"] == "merge_commit"
    assert broker.calls[0][1]["close_source_branch"] is False


def test_merge_pull_request_uses_supplied_message_when_given(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    service.merge_pull_request("42", message="Ship it", merge_strategy="squash", close_source_branch=True, yes=True)

    assert broker.calls[0][1]["message"] == "Ship it"
    assert broker.calls[0][1]["merge_strategy"] == "squash"
    assert broker.calls[0][1]["close_source_branch"] is True


def test_merge_pull_request_rejects_unknown_merge_strategy(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    with pytest.raises(
        InputValidationError, match=r"--merge-strategy must be one of: fast_forward, merge_commit, squash\."
    ):
        service.merge_pull_request("42", merge_strategy="rebase")

    assert broker.calls == []


def test_merge_pull_request_dry_run_never_calls_broker(config, tmp_path) -> None:
    broker = FakeBroker()
    service = DevtoolsService(config, tmp_path, broker)

    result = service.merge_pull_request("42", dry_run=True)

    assert isinstance(result, PreviewResult)
    assert broker.calls == []


def test_create_pull_request_forwards_description_reviewer_and_close_source_branch(config, tmp_path) -> None:
    broker = FakeBroker()
    verification = FakeVerification()
    service = DevtoolsService(config, tmp_path, broker, verification_runner=verification)

    service.create_pull_request(
        "A PR",
        source_branch="feature/x",
        description="Adds caching",
        reviewer=["alice"],
        close_source_branch=True,
        yes=True,
    )

    payload = broker.calls[0][1]
    assert payload["description"] == "Adds caching"
    # Config's default reviewer ("reviewer", from the `config` fixture) is merged in at the
    # adapter layer, not here — the workflow payload carries only the caller-supplied list.
    assert payload["reviewers"] == ["alice"]
    assert payload["close_source_branch"] is True


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
