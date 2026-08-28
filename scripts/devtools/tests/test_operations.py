from __future__ import annotations

import pytest

import just_dev.operations as operations
from just_dev.errors import AuthenticationError, InputValidationError
from just_dev.models import PullRequestResult
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

    def search_issues(self, token: str, parameters: dict) -> dict:
        self.calls.append(("search", self.cloud_id, token, parameters))
        return {"issues": [], "parameters": parameters}

    def update_issue(self, token: str, issue_id_or_key: str, request: dict) -> dict:
        self.calls.append(("update", self.cloud_id, token, issue_id_or_key, request))
        return {"key": issue_id_or_key, "request": request}

    def delete_issue(self, token: str, issue_id_or_key: str, parameters: dict) -> dict:
        self.calls.append(("delete", self.cloud_id, token, issue_id_or_key, parameters))
        return {"key": issue_id_or_key, "parameters": parameters}

    def assign_issue(self, token: str, issue_id_or_key: str, account_id: str) -> dict:
        self.calls.append(("assign", self.cloud_id, token, issue_id_or_key, account_id))
        return {"issue_id_or_key": issue_id_or_key, "assignee": account_id}

    def comment_issue(self, token: str, issue_id_or_key: str, request: dict) -> dict:
        self.calls.append(("comment", self.cloud_id, token, issue_id_or_key, request))
        return {"issue_id_or_key": issue_id_or_key, "request": request}

    def attach_file(self, token: str, issue_id_or_key: str, filename: str, content_b64: str) -> dict:
        self.calls.append(("attach", self.cloud_id, token, issue_id_or_key, filename, content_b64))
        return {"issue_id_or_key": issue_id_or_key, "filename": filename}

    def list_transitions(self, token: str, issue_id_or_key: str) -> dict:
        self.calls.append(("list_transitions", self.cloud_id, token, issue_id_or_key))
        return {"transitions": [{"id": "11", "to": {"name": "Done"}}]}

    def transition_issue(self, token: str, issue_id_or_key: str, transition_id: str) -> dict:
        self.calls.append(("transition", self.cloud_id, token, issue_id_or_key, transition_id))
        return {"issue_id_or_key": issue_id_or_key, "transition_id": transition_id}

    def verify_credentials(self, token: str) -> dict:
        self.calls.append(("verify_credentials", self.cloud_id, token))
        return {"accountId": "abc123"}


class FakeBitbucketAdapter:
    calls: list[tuple] = []

    def __init__(self, settings) -> None:
        self.settings = settings

    def create_pull_request(
        self,
        token: str,
        title: str,
        source_branch: str,
        *,
        description: str | None = None,
        reviewers: tuple = (),
        close_source_branch: bool = False,
    ) -> PullRequestResult:
        self.calls.append(
            ("create_pull_request", token, title, source_branch, description, tuple(reviewers), close_source_branch)
        )
        return PullRequestResult(id=1, title=title, source_branch=source_branch, target_branch="main")

    def approve_pull_request(self, token: str, pull_request_id: str) -> dict:
        self.calls.append(("approve_pull_request", token, pull_request_id))
        return {"pull_request_id": pull_request_id, "approved": True}

    def merge_pull_request(
        self, token: str, pull_request_id: str, *, message: str, merge_strategy: str, close_source_branch: bool
    ) -> dict:
        self.calls.append(("merge_pull_request", token, pull_request_id, message, merge_strategy, close_source_branch))
        return {"pull_request_id": pull_request_id, "merged": True}

    def decline_pull_request(self, token: str, pull_request_id: str) -> dict:
        self.calls.append(("decline_pull_request", token, pull_request_id))
        return {"pull_request_id": pull_request_id, "declined": True}

    def add_pull_request_comment(self, token: str, pull_request_id: str, text: str) -> dict:
        self.calls.append(("add_pull_request_comment", token, pull_request_id, text))
        return {"pull_request_id": pull_request_id, "text": text}

    def add_pull_request_reviewer(self, token: str, pull_request_id: str, reviewer: str) -> dict:
        self.calls.append(("add_pull_request_reviewer", token, pull_request_id, reviewer))
        return {"pull_request_id": pull_request_id, "reviewer": reviewer}


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


def test_jira_search_issues_operation_forwards_parameters_to_the_adapter(config, monkeypatch) -> None:
    FakeJiraAdapter.calls = []
    monkeypatch.setattr(operations, "JiraAdapter", FakeJiraAdapter)
    payload = {
        "config": config.model_dump(mode="json"),
        "parameters": {"jql": "project = DEV", "fields": "summary,status", "maxResults": 25},
    }

    result = execute_operation({"jira": "jira-secret"}, "jira.search_issues", payload)

    assert result["parameters"] == payload["parameters"]
    assert FakeJiraAdapter.calls == [("search", config.atlassian.cloud_id, "jira-secret", payload["parameters"])]


def test_jira_search_issues_operation_forwards_parameters_using_a_ci_token(config, monkeypatch) -> None:
    FakeJiraAdapter.calls = []
    monkeypatch.setattr(operations, "JiraAdapter", FakeJiraAdapter)
    payload = {
        "config": config.model_dump(mode="json"),
        "parameters": {"jql": "project = DEV"},
        "__just_dev_ci": True,
    }

    result = execute_operation({"jira": "ci-secret"}, "jira.search_issues", payload)

    assert result["parameters"] == {"jql": "project = DEV"}
    assert FakeJiraAdapter.calls == [("search", config.atlassian.cloud_id, "ci-secret", {"jql": "project = DEV"})]


def test_jira_assign_comment_attach_and_transition_operations_forward_to_the_adapter(config, monkeypatch) -> None:
    FakeJiraAdapter.calls = []
    monkeypatch.setattr(operations, "JiraAdapter", FakeJiraAdapter)
    payload = {"config": config.model_dump(mode="json")}
    tokens = {"jira": "jira-secret"}

    assign = execute_operation(
        tokens, "jira.assign_issue", {**payload, "issue_id_or_key": "DEV-1", "assignee": "acc-123"}
    )
    comment = execute_operation(
        tokens, "jira.comment_issue", {**payload, "issue_id_or_key": "DEV-1", "comment": "Looks good"}
    )
    attached = execute_operation(
        tokens,
        "jira.attach_file",
        {**payload, "issue_id_or_key": "DEV-1", "filename": "notes.txt", "content_b64": "ZmlsZQ=="},
    )
    transitions = execute_operation(tokens, "jira.list_transitions", {**payload, "issue_id_or_key": "DEV-1"})
    transition = execute_operation(
        tokens, "jira.transition_issue", {**payload, "issue_id_or_key": "DEV-1", "transition_id": "11"}
    )

    assert assign["assignee"] == "acc-123"
    assert comment["request"]["body"]["content"][0]["content"][0]["text"] == "Looks good"
    assert attached == {"issue_id_or_key": "DEV-1", "filename": "notes.txt"}
    assert transitions["transitions"][0]["to"]["name"] == "Done"
    assert transition["transition_id"] == "11"
    assert [call[0] for call in FakeJiraAdapter.calls] == [
        "assign",
        "comment",
        "attach",
        "list_transitions",
        "transition",
    ]
    assert FakeJiraAdapter.calls[2] == (
        "attach",
        "00000000-0000-4000-8000-000000000123",
        "jira-secret",
        "DEV-1",
        "notes.txt",
        "ZmlsZQ==",
    )
    assert FakeJiraAdapter.calls[0] == (
        "assign",
        "00000000-0000-4000-8000-000000000123",
        "jira-secret",
        "DEV-1",
        "acc-123",
    )


def test_jira_verify_credentials_operation_forwards_the_token_to_the_adapter(config, monkeypatch) -> None:
    FakeJiraAdapter.calls = []
    monkeypatch.setattr(operations, "JiraAdapter", FakeJiraAdapter)
    payload = {"config": config.model_dump(mode="json")}

    result = execute_operation({"jira": "jira-secret"}, "jira.verify_credentials", payload)

    assert result == {"accountId": "abc123"}
    assert FakeJiraAdapter.calls == [("verify_credentials", config.atlassian.cloud_id, "jira-secret")]


def test_jira_verify_credentials_missing_local_and_ci_tokens_explain_the_respective_recovery_path(config) -> None:
    payload = {"config": config.model_dump(mode="json")}

    with pytest.raises(AuthenticationError, match=r"configure-auth --entry jira=KEEPASS_ENTRY_UUID") as local:
        execute_operation({}, "jira.verify_credentials", payload)
    assert "unlock-secrets" in str(local.value)

    with pytest.raises(AuthenticationError, match="JUST_DEV_CI_JIRA_TOKEN"):
        execute_operation({}, "jira.verify_credentials", {**payload, "__just_dev_ci": True})


def test_jira_update_body_parses_comma_separated_labels_and_wraps_priority() -> None:
    body = operations._jira_update_body({"request": {}, "labels": " a, b ,,c", "priority": " High "})

    assert body["fields"]["labels"] == ["a", "b", "c"]
    assert body["fields"]["priority"] == {"name": "High"}


def test_jira_update_body_omits_labels_and_priority_when_not_supplied() -> None:
    body = operations._jira_update_body({"request": {}, "summary": "New summary"})

    assert "labels" not in body["fields"]
    assert "priority" not in body["fields"]


def test_jira_update_body_named_flags_silently_override_matching_positional_request_fields() -> None:
    """update-jira-issue accepts both a positional JSON request and named flags (--summary etc.) in the
    same call; a caller relying on the positional body to win (e.g. a hand-built ADF description) would
    lose that value with no warning, so this pins the current last-write-wins precedence exactly."""
    body = operations._jira_update_body(
        {
            "request": {"fields": {"summary": "from positional", "labels": ["kept"]}},
            "summary": "from flag",
        }
    )

    assert body["fields"]["summary"] == "from flag"
    assert body["fields"]["labels"] == ["kept"]


def test_bitbucket_create_pull_request_forwards_description_reviewers_and_close_source_branch(
    config, monkeypatch
) -> None:
    FakeBitbucketAdapter.calls = []
    monkeypatch.setattr(operations, "BitbucketAdapter", FakeBitbucketAdapter)
    payload = {"config": config.model_dump(mode="json")}

    result = execute_operation(
        {"bitbucket": "bb-secret"},
        "bitbucket.create_pull_request",
        {
            **payload,
            "title": "Add caching",
            "source_branch": "feature/caching",
            "description": "Adds an LRU cache.",
            "reviewers": ["alice", "bob"],
            "close_source_branch": True,
        },
    )

    assert result["title"] == "Add caching"
    assert FakeBitbucketAdapter.calls == [
        (
            "create_pull_request",
            "bb-secret",
            "Add caching",
            "feature/caching",
            "Adds an LRU cache.",
            ("alice", "bob"),
            True,
        )
    ]


def test_bitbucket_create_pull_request_defaults_description_and_reviewers_when_omitted(config, monkeypatch) -> None:
    FakeBitbucketAdapter.calls = []
    monkeypatch.setattr(operations, "BitbucketAdapter", FakeBitbucketAdapter)
    payload = {"config": config.model_dump(mode="json")}

    execute_operation(
        {"bitbucket": "bb-secret"},
        "bitbucket.create_pull_request",
        {**payload, "title": "Add caching", "source_branch": "feature/caching"},
    )

    assert FakeBitbucketAdapter.calls == [
        ("create_pull_request", "bb-secret", "Add caching", "feature/caching", None, (), False)
    ]


def test_bitbucket_new_pull_request_operations_forward_to_the_adapter(config, monkeypatch) -> None:
    FakeBitbucketAdapter.calls = []
    monkeypatch.setattr(operations, "BitbucketAdapter", FakeBitbucketAdapter)
    payload = {"config": config.model_dump(mode="json")}
    tokens = {"bitbucket": "bb-secret"}

    approve = execute_operation(tokens, "bitbucket.approve_pull_request", {**payload, "pull_request_id": "42"})
    merge = execute_operation(
        tokens,
        "bitbucket.merge_pull_request",
        {
            **payload,
            "pull_request_id": "42",
            "message": "Merge it",
            "merge_strategy": "squash",
            "close_source_branch": True,
        },
    )
    decline = execute_operation(tokens, "bitbucket.decline_pull_request", {**payload, "pull_request_id": "42"})
    comment = execute_operation(
        tokens, "bitbucket.add_pull_request_comment", {**payload, "pull_request_id": "42", "comment": "LGTM"}
    )
    reviewer = execute_operation(
        tokens, "bitbucket.add_pull_request_reviewer", {**payload, "pull_request_id": "42", "reviewer": "alice"}
    )

    assert approve["approved"] is True
    assert merge["merged"] is True
    assert decline["declined"] is True
    assert comment["text"] == "LGTM"
    assert reviewer["reviewer"] == "alice"
    assert [call[0] for call in FakeBitbucketAdapter.calls] == [
        "approve_pull_request",
        "merge_pull_request",
        "decline_pull_request",
        "add_pull_request_comment",
        "add_pull_request_reviewer",
    ]
    assert FakeBitbucketAdapter.calls[1] == ("merge_pull_request", "bb-secret", "42", "Merge it", "squash", True)


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


def test_search_jira_issues_missing_local_and_ci_tokens_explain_the_respective_recovery_path(config) -> None:
    payload = {"config": config.model_dump(mode="json"), "parameters": {"jql": "project = DEV"}}

    with pytest.raises(AuthenticationError, match=r"configure-auth --entry jira=KEEPASS_ENTRY_UUID") as local:
        execute_operation({}, "jira.search_issues", payload)
    assert "unlock-secrets" in str(local.value)

    with pytest.raises(AuthenticationError, match="JUST_DEV_CI_JIRA_TOKEN"):
        execute_operation({}, "jira.search_issues", {**payload, "__just_dev_ci": True})
