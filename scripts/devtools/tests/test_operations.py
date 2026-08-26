from __future__ import annotations

import pytest

import just_dev.operations as operations
from just_dev.errors import AuthenticationError, InputValidationError
from just_dev.operations import execute_operation


class FakeJiraAdapter:
    calls: list[tuple] = []

    def __init__(self, cloud_id: str) -> None:
        self.cloud_id = cloud_id

    def create_issue(self, token: str, request: dict) -> dict:
        self.calls.append(("create", self.cloud_id, token, request))
        return {"key": "DEV-1", "request": request}

    def read_issue(self, token: str, issue_id_or_key: str, parameters: dict) -> dict:
        self.calls.append(("read", self.cloud_id, token, issue_id_or_key, parameters))
        return {"key": issue_id_or_key, "parameters": parameters}

    def update_issue(self, token: str, issue_id_or_key: str, request: dict) -> dict:
        self.calls.append(("update", self.cloud_id, token, issue_id_or_key, request))
        return {"key": issue_id_or_key, "request": request}

    def delete_issue(self, token: str, issue_id_or_key: str, parameters: dict) -> dict:
        self.calls.append(("delete", self.cloud_id, token, issue_id_or_key, parameters))
        return {"key": issue_id_or_key, "parameters": parameters}


def test_jira_crud_operations_forward_complete_request_objects(config, monkeypatch) -> None:
    FakeJiraAdapter.calls = []
    monkeypatch.setattr(operations, "JiraAdapter", FakeJiraAdapter)
    payload = {"config": config.model_dump(mode="json")}
    tokens = {"jira": "jira-secret"}

    create = execute_operation(
        tokens,
        "jira.create_issue",
        {
            **payload,
            "preset": "bug",
            "summary": "New issue",
            "description": "Steps to reproduce",
            "fields": {"customfield_10001": {"value": "Blue"}},
        },
    )
    read = execute_operation(
        tokens,
        "jira.read_issue",
        {
            **payload,
            "issue_id_or_key": "DEV-1",
            "parameters": {"fields": "summary,customfield_10001", "expand": "names,schema"},
        },
    )
    update = execute_operation(
        tokens,
        "jira.update_issue",
        {
            **payload,
            "issue_id_or_key": "DEV-1",
            "summary": "Updated summary",
            "request": {
                "fields": {"customfield_10001": {"value": "Green"}},
                "update": {"labels": [{"remove": "triaged"}]},
                "notifyUsers": False,
            },
        },
    )
    delete = execute_operation(
        tokens,
        "jira.delete_issue",
        {**payload, "issue_id_or_key": "DEV-1", "parameters": {"deleteSubtasks": True}},
    )

    assert create["request"]["fields"]["project"] == {"key": "DEV"}
    assert create["request"]["fields"]["issuetype"] == {"name": "Task"}
    assert create["request"]["fields"]["labels"] == ["auto-filed"]
    assert create["request"]["fields"]["summary"] == "New issue"
    assert create["request"]["fields"]["description"]["content"][0]["content"][0]["text"] == "Steps to reproduce"
    assert create["request"]["fields"]["customfield_10001"] == {"value": "Blue"}
    assert read["parameters"]["expand"] == "names,schema"
    assert update["request"]["fields"]["summary"] == "Updated summary"
    assert update["request"]["fields"]["customfield_10001"] == {"value": "Green"}
    assert update["request"]["update"]["labels"] == [{"remove": "triaged"}]
    assert update["request"]["notifyUsers"] is False
    assert delete["parameters"] == {"deleteSubtasks": True}
    assert [call[0] for call in FakeJiraAdapter.calls] == ["create", "read", "update", "delete"]


def test_jira_create_issue_preset_fields_cannot_be_overridden_by_custom_fields(config, monkeypatch) -> None:
    FakeJiraAdapter.calls = []
    monkeypatch.setattr(operations, "JiraAdapter", FakeJiraAdapter)
    payload = {"config": config.model_dump(mode="json")}

    result = execute_operation(
        {"jira": "jira-secret"},
        "jira.create_issue",
        {
            **payload,
            "preset": "bug",
            "summary": "Issue",
            "fields": {"project": {"key": "OTHER"}, "issuetype": {"name": "Bug"}},
        },
    )

    assert result["request"]["fields"]["project"] == {"key": "DEV"}
    assert result["request"]["fields"]["issuetype"] == {"name": "Task"}


def test_legacy_jira_get_operation_is_not_allowlisted(config) -> None:
    with pytest.raises(InputValidationError, match="not allowed"):
        execute_operation(
            {"jira": "jira-secret"},
            "jira.get_issue",
            {"config": config.model_dump(mode="json"), "key": "DEV-1"},
        )


def test_missing_local_and_ci_tokens_explain_the_respective_recovery_path(config) -> None:
    payload = {"config": config.model_dump(mode="json"), "issue_id_or_key": "DEV-1", "parameters": {}}

    with pytest.raises(AuthenticationError, match=r"configure-auth --entry jira=KEEPASS_ENTRY_UUID") as local:
        execute_operation({}, "jira.read_issue", payload)
    assert "unlock-secrets" in str(local.value)

    with pytest.raises(AuthenticationError, match="JUST_DEV_CI_JIRA_TOKEN"):
        execute_operation({}, "jira.read_issue", {**payload, "__just_dev_ci": True})
