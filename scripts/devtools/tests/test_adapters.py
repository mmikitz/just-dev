from __future__ import annotations

import base64

import pytest
from atlassian.errors import ApiPermissionError
from requests.exceptions import RequestException, Timeout

import just_dev.adapters as adapters
from just_dev.adapters import BitbucketAdapter, ConfluenceAdapter, JenkinsAdapter, JiraAdapter
from just_dev.errors import (
    AuthenticationError,
    ConflictError,
    InputValidationError,
    NetworkError,
    PermissionDeniedError,
)
from just_dev.models import BitbucketSettings, ConfluencePreset, JenkinsPreset, JenkinsSettings


class FakeJira:
    def __init__(self) -> None:
        self.post_calls: list[tuple] = []
        self.get_calls: list[tuple] = []
        self.put_calls: list[tuple] = []
        self.delete_calls: list[tuple] = []
        self.attachment_calls: list[tuple] = []

    def resource_url(self, resource, api_root=None, api_version=None):
        return f"rest/api/3/{resource}"

    def post(self, path, *, data=None, params=None):
        self.post_calls.append((path, data, params))
        return {"id": "10001", "key": "DEV-1", "self": "https://jira.test/DEV-1"}

    def get(self, path, *, params=None):
        self.get_calls.append((path, params))
        return {
            "key": "DEV-1",
            "fields": {
                "summary": "A summary",
                "status": {"name": "In Progress"},
                "assignee": {"displayName": "Ada"},
            },
        }

    def put(self, path, *, data=None, params=None):
        self.put_calls.append((path, data, params))
        return None

    def delete(self, path, *, params=None):
        self.delete_calls.append((path, params))
        return None

    def add_attachment_object(self, issue_key, attachment):
        self.attachment_calls.append((issue_key, attachment.name, attachment.read()))
        return [{"id": "20001", "filename": attachment.name}]


class FakeBitbucket:
    def __init__(self, pull_requests: list[dict]) -> None:
        self.pull_requests = pull_requests
        self.list_calls: list[tuple] = []
        self.create_calls: list[tuple] = []
        self.resource_url_calls: list[tuple] = []
        self.post_calls: list[tuple] = []
        self.merge_calls: list[tuple] = []
        self.decline_calls: list[tuple] = []
        self.comment_calls: list[tuple] = []
        self.participant_calls: list[tuple] = []

    def get_pull_requests(self, *args, **kwargs):
        self.list_calls.append((args, kwargs))
        yield from self.pull_requests

    def create_pull_request(self, *args):
        self.create_calls.append(args)
        return {
            "id": 6,
            "title": args[2]["title"],
            "source": args[2]["source"],
            "destination": args[2]["destination"],
            "links": {"html": {"href": "https://bitbucket.test/pr/6"}},
        }

    def get_pull_request(self, *args):
        return {
            "id": args[-1],
            "title": "Existing",
            "source": {"branch": {"name": "feature/x"}},
            "destination": {"branch": {"name": "main"}},
        }

    def resource_url(self, resource, api_root=None, api_version=None):
        self.resource_url_calls.append((resource, api_root, api_version))
        return f"2.0/{resource}"

    def post(self, path, *, data=None, params=None):
        self.post_calls.append((path, data, params))
        return {"approved": True}

    def merge_pull_request(self, *args, **kwargs):
        self.merge_calls.append((args, kwargs))
        return {"id": args[2], "state": "MERGED"}

    def decline_pull_request(self, *args):
        self.decline_calls.append(args)
        return {"id": args[2], "state": "DECLINED"}

    def add_pull_request_comment(self, *args):
        self.comment_calls.append(args)
        return {"id": 99, "content": {"raw": args[3]}}

    def assign_pull_request_participant_role(self, *args):
        self.participant_calls.append(args)
        return {"role": args[3], "user": {"name": args[4]}}


class FakeJenkins:
    def __init__(self) -> None:
        self.build_calls: list[tuple] = []
        self.queue_calls: list[int] = []
        self.info_calls: list[tuple[str, int]] = []

    def build_job(self, name, parameters=None, token=None):
        self.build_calls.append((name, parameters, token))
        return 18

    def get_queue_item(self, number, depth=0):
        self.queue_calls.append(number)
        return {"executable": {"number": 4}}

    def get_build_info(self, name, number, depth=0):
        self.info_calls.append((name, number))
        return {"building": False, "result": "SUCCESS", "url": "https://jenkins.test/job/test/4/"}


class FakeConfluence:
    def __init__(self) -> None:
        self.get_calls: list[tuple] = []
        self.put_calls: list[tuple] = []

    def get(self, path, *, params=None):
        self.get_calls.append((path, params))
        return {
            "id": "42",
            "title": "Release notes",
            "version": {"number": 3},
            "_links": {"webui": "/wiki/spaces/DEV/pages/42"},
            "body": {"storage": {"value": "<p>Old</p>"}},
        }

    def resource_url(self, resource, api_root=None, api_version=None):
        return f"wiki/api/v2/{resource}"

    def put(self, path, *, data=None):
        self.put_calls.append((path, data))
        return {
            "id": "42",
            "title": data["title"],
            "version": {"number": data["version"]["number"]},
            "_links": {"webui": "/wiki/spaces/DEV/pages/42"},
        }


def test_jira_adapter_uses_atlassian_sdk_with_scoped_gateway(monkeypatch) -> None:
    client = FakeJira()
    constructor_calls: list[tuple[tuple, dict]] = []

    def jira_constructor(*args, **kwargs):
        constructor_calls.append((args, kwargs))
        return client

    monkeypatch.setattr(adapters, "Jira", jira_constructor)

    adapter = JiraAdapter("cloud id")
    result = adapter.create_issue(
        "secret",
        {
            "fields": {"project": {"key": "DEV"}, "issuetype": {"name": "Task"}, "summary": "A summary"},
            "update": {"labels": [{"add": "x"}]},
            "updateHistory": True,
        },
    )
    read = adapter.read_issue("secret", "DEV-1", {"fields": ["summary", "customfield_10001"], "failFast": False})
    updated = adapter.update_issue(
        "secret",
        "DEV-1",
        {"fields": {"customfield_10001": "new"}, "notifyUsers": False, "returnIssue": True, "expand": "renderedFields"},
    )
    deleted = adapter.delete_issue("secret", "DEV-1", {"deleteSubtasks": True})

    assert result == {"id": "10001", "key": "DEV-1", "self": "https://jira.test/DEV-1"}
    assert read["fields"]["assignee"]["displayName"] == "Ada"
    assert updated == {"issue_id_or_key": "DEV-1", "updated": True}
    assert deleted == {"issue_id_or_key": "DEV-1", "deleted": True}
    expected_constructor_call = (
        (),
        {
            "url": "https://api.atlassian.com/ex/jira/cloud%20id",
            "token": "secret",
            "cloud": True,
            "api_version": "3",
        },
    )
    assert constructor_calls == [expected_constructor_call] * 4
    assert client.post_calls == [
        (
            "rest/api/3/issue",
            {
                "fields": {"project": {"key": "DEV"}, "issuetype": {"name": "Task"}, "summary": "A summary"},
                "update": {"labels": [{"add": "x"}]},
            },
            {"updateHistory": True},
        )
    ]
    assert client.get_calls == [
        ("rest/api/3/issue/DEV-1", {"fields": ["summary", "customfield_10001"], "failFast": False})
    ]
    assert client.put_calls == [
        (
            "rest/api/3/issue/DEV-1",
            {"fields": {"customfield_10001": "new"}},
            {"notifyUsers": False, "returnIssue": True, "expand": "renderedFields"},
        )
    ]
    assert client.delete_calls == [("rest/api/3/issue/DEV-1", {"deleteSubtasks": True})]


def test_jira_adapter_search_issues_calls_the_enhanced_jql_search_endpoint(monkeypatch) -> None:
    class FakeJiraSearch:
        def __init__(self) -> None:
            self.get_calls: list[tuple] = []

        def resource_url(self, resource, api_root=None, api_version=None):
            return f"rest/api/3/{resource}"

        def get(self, path, *, params=None):
            self.get_calls.append((path, params))
            return {
                "issues": [{"key": "DEV-1", "fields": {"summary": "A summary"}}],
                "nextPageToken": "CAEaAggD",
                "isLast": False,
            }

    client = FakeJiraSearch()
    monkeypatch.setattr(adapters, "Jira", lambda *args, **kwargs: client)
    adapter = JiraAdapter("cloud id")

    result = adapter.search_issues("secret", {"jql": "project = DEV", "fields": "summary,status", "maxResults": 25})

    assert result["issues"] == [{"key": "DEV-1", "fields": {"summary": "A summary"}}]
    assert result["nextPageToken"] == "CAEaAggD"
    assert result["isLast"] is False
    assert client.get_calls == [
        ("rest/api/3/search/jql", {"jql": "project = DEV", "fields": "summary,status", "maxResults": 25})
    ]


def test_jira_adapter_assigns_comments_lists_transitions_and_transitions_issue(monkeypatch) -> None:
    client = FakeJira()
    monkeypatch.setattr(adapters, "Jira", lambda *args, **kwargs: client)
    adapter = JiraAdapter("cloud id")
    comment_body = {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "hello"}]}],
    }

    assigned = adapter.assign_issue("secret", "DEV-1", "abc123")
    commented = adapter.comment_issue("secret", "DEV-1", {"body": comment_body})
    transitions = adapter.list_transitions("secret", "DEV-1")
    transitioned = adapter.transition_issue("secret", "DEV-1", "31")

    assert assigned == {"issue_id_or_key": "DEV-1", "assignee": "abc123"}
    assert commented == {"id": "10001", "key": "DEV-1", "self": "https://jira.test/DEV-1"}
    assert transitions["fields"]["status"]["name"] == "In Progress"
    assert transitioned == {"id": "10001", "key": "DEV-1", "self": "https://jira.test/DEV-1"}
    assert client.put_calls == [("rest/api/3/issue/DEV-1/assignee", {"accountId": "abc123"}, None)]
    assert client.post_calls == [
        ("rest/api/3/issue/DEV-1/comment", {"body": comment_body}, None),
        ("rest/api/3/issue/DEV-1/transitions", {"transition": {"id": "31"}}, None),
    ]
    assert client.get_calls == [("rest/api/3/issue/DEV-1/transitions", None)]


def test_jira_adapter_attach_file_decodes_base64_and_posts_the_named_attachment(monkeypatch) -> None:
    client = FakeJira()
    monkeypatch.setattr(adapters, "Jira", lambda *args, **kwargs: client)
    adapter = JiraAdapter("cloud id")
    encoded = base64.b64encode(b"file contents").decode("ascii")

    result = adapter.attach_file("secret", "DEV-1", "notes.txt", encoded)

    assert result == {
        "issue_id_or_key": "DEV-1",
        "filename": "notes.txt",
        "attachments": [{"id": "20001", "filename": "notes.txt"}],
    }
    assert client.attachment_calls == [("DEV-1", "notes.txt", b"file contents")]


def test_jira_adapter_assign_and_transition_fall_back_when_jira_returns_no_content() -> None:
    class EmptyResponseJira:
        def resource_url(self, resource, api_root=None, api_version=None):
            return f"rest/api/3/{resource}"

        def put(self, path, *, data=None, params=None):
            return None

        def post(self, path, *, data=None, params=None):
            return None

    adapter = JiraAdapter("cloud", lambda token: EmptyResponseJira())

    assert adapter.assign_issue("secret", "DEV-1", "abc123") == {
        "issue_id_or_key": "DEV-1",
        "assignee": "abc123",
    }
    assert adapter.transition_issue("secret", "DEV-1", "31") == {
        "issue_id_or_key": "DEV-1",
        "transitioned": True,
    }


def test_jira_adapter_assign_issue_resolves_an_email_to_its_account_id() -> None:
    class FakeJiraUsers:
        def __init__(self, users: list[dict]) -> None:
            self.users = users
            self.put_calls: list[tuple] = []

        def resource_url(self, resource, api_root=None, api_version=None):
            return f"rest/api/3/{resource}"

        def user_find_by_user_string(self, *, query):
            return [user for user in self.users if user["emailAddress"].lower() == query.lower()]

        def put(self, path, *, data=None, params=None):
            self.put_calls.append((path, data, params))
            return None

    client = FakeJiraUsers([{"accountId": "abc123", "emailAddress": "ada@example.com", "displayName": "Ada"}])
    adapter = JiraAdapter("cloud", lambda token: client)

    result = adapter.assign_issue("secret", "DEV-1", "ada@example.com")

    assert result == {"issue_id_or_key": "DEV-1", "assignee": "abc123"}
    assert client.put_calls == [("rest/api/3/issue/DEV-1/assignee", {"accountId": "abc123"}, None)]


def test_jira_adapter_assign_issue_rejects_an_email_with_no_match() -> None:
    class FakeJiraUsers:
        def resource_url(self, resource, api_root=None, api_version=None):
            return f"rest/api/3/{resource}"

        def user_find_by_user_string(self, *, query):
            return []

    adapter = JiraAdapter("cloud", lambda token: FakeJiraUsers())

    with pytest.raises(InputValidationError, match="No Jira user found"):
        adapter.assign_issue("secret", "DEV-1", "nobody@example.com")


def test_jira_adapter_assign_issue_rejects_an_ambiguous_email() -> None:
    class FakeJiraUsers:
        def resource_url(self, resource, api_root=None, api_version=None):
            return f"rest/api/3/{resource}"

        def user_find_by_user_string(self, *, query):
            return [
                {"accountId": "abc123", "emailAddress": "team@example.com"},
                {"accountId": "def456", "emailAddress": "team@example.com"},
            ]

    adapter = JiraAdapter("cloud", lambda token: FakeJiraUsers())

    with pytest.raises(InputValidationError, match="matched multiple Jira users"):
        adapter.assign_issue("secret", "DEV-1", "team@example.com")


def test_bitbucket_adapter_approves_via_native_cloud_endpoint_without_a_user_slug() -> None:
    client = FakeBitbucket([])
    settings = BitbucketSettings(workspace="w", repository="r", username="u")

    result = BitbucketAdapter(settings, lambda token: client).approve_pull_request("token", 42)

    assert result == {"approved": True}
    assert client.resource_url_calls == [("repositories/w/r/pullrequests/42/approve", None, None)]
    assert client.post_calls == [("2.0/repositories/w/r/pullrequests/42/approve", {"approved": True}, None)]


def test_bitbucket_adapter_merges_declines_comments_and_assigns_reviewer() -> None:
    client = FakeBitbucket([])
    settings = BitbucketSettings(workspace="w", repository="r", username="u")
    adapter = BitbucketAdapter(settings, lambda token: client)

    merged = adapter.merge_pull_request(
        "token", 42, message="Merge it", merge_strategy="squash", close_source_branch=True
    )
    declined = adapter.decline_pull_request("token", 42)
    commented = adapter.add_pull_request_comment("token", 42, "Looks good")
    assigned = adapter.add_pull_request_reviewer("token", 42, "alice")

    assert merged == {"id": "42", "state": "MERGED"}
    assert declined == {"id": "42", "state": "DECLINED"}
    assert commented == {"id": 99, "content": {"raw": "Looks good"}}
    assert assigned == {"role": "REVIEWER", "user": {"name": "alice"}}
    assert client.merge_calls == [
        (
            ("w", "r", "42", "Merge it"),
            {"close_source_branch": True, "merge_strategy": "squash", "pr_version": None},
        )
    ]
    assert client.decline_calls == [("w", "r", "42", None)]
    assert client.comment_calls == [("w", "r", "42", "Looks good")]
    assert client.participant_calls == [("w", "r", 42, "REVIEWER", "alice")]


def test_bitbucket_adapter_create_pull_request_unions_config_and_explicit_reviewers() -> None:
    client = FakeBitbucket([])
    settings = BitbucketSettings(workspace="w", repository="r", username="u", reviewers=["bob"])

    result = BitbucketAdapter(settings, lambda token: client).create_pull_request(
        "token", "New", "feature/x", description="desc", reviewers=["alice", "bob"], close_source_branch=True
    )

    assert result.id == 6
    payload = client.create_calls[0][2]
    assert payload["description"] == "desc"
    assert payload["reviewers"] == [{"username": "bob"}, {"username": "alice"}]
    assert payload["close_source_branch"] is True


def test_bitbucket_adapter_create_pull_request_skips_new_fields_when_an_open_pr_already_exists() -> None:
    client = FakeBitbucket(
        [
            {
                "id": 5,
                "title": "Already open",
                "source": {"branch": {"name": "feature/x"}},
                "destination": {"branch": {"name": "main"}},
            }
        ]
    )
    settings = BitbucketSettings(workspace="w", repository="r", username="u", reviewers=["bob"])

    result = BitbucketAdapter(settings, lambda token: client).create_pull_request(
        "token", "New", "feature/x", description="desc", reviewers=["alice"], close_source_branch=True
    )

    assert result.existing is True
    assert client.create_calls == []


def test_bitbucket_adapter_uses_sdk_pagination_before_creating() -> None:
    client = FakeBitbucket(
        [
            {
                "id": 5,
                "title": "Already open",
                "source": {"branch": {"name": "feature/x"}},
                "destination": {"branch": {"name": "main"}},
            }
        ]
    )
    settings = BitbucketSettings(workspace="w", repository="r", username="u")

    result = BitbucketAdapter(settings, lambda token: client).create_pull_request("token", "New", "feature/x")

    assert result.existing is True
    assert client.list_calls == [(("w", "r"), {"state": "OPEN", "limit": 50})]
    assert client.create_calls == []


def test_bitbucket_adapter_constructs_cloud_sdk_from_v2_api_base(monkeypatch) -> None:
    client = FakeBitbucket([])
    constructor_calls: list[tuple[tuple, dict]] = []

    def bitbucket_constructor(*args, **kwargs):
        constructor_calls.append((args, kwargs))
        return client

    monkeypatch.setattr(adapters, "Bitbucket", bitbucket_constructor)
    settings = BitbucketSettings(
        workspace="workspace",
        repository="repository",
        username="developer@example.test",
    )

    assert BitbucketAdapter(settings).find_open_pull_request("secret", "feature/x") is None
    assert constructor_calls == [
        (
            (),
            {
                "url": "https://api.bitbucket.org",
                "username": "developer@example.test",
                "password": "secret",
                "cloud": True,
            },
        )
    ]
    assert client.api_root == ""
    assert client.api_version == "2.0"


def test_jenkins_adapter_uses_python_jenkins_for_builds_and_status(monkeypatch) -> None:
    client = FakeJenkins()
    constructor_calls: list[tuple[tuple, dict]] = []

    def jenkins_constructor(*args, **kwargs):
        constructor_calls.append((args, kwargs))
        return client

    monkeypatch.setattr(adapters.jenkins, "Jenkins", jenkins_constructor)
    settings = JenkinsSettings(url="https://jenkins.test/", username="jenkins-user")
    adapter = JenkinsAdapter(settings)
    preset = JenkinsPreset(job="folder/job/test", allowed_parameters=["REF"])

    queued = adapter.run_build("secret", "test", preset, {"REF": "main"})
    status = adapter.get_build_status("secret", "test", preset, "18")

    assert constructor_calls == [
        (("https://jenkins.test",), {"username": "jenkins-user", "password": "secret", "timeout": 30}),
        (("https://jenkins.test",), {"username": "jenkins-user", "password": "secret", "timeout": 30}),
    ]
    assert queued.queue_id == 18
    assert queued.url == "https://jenkins.test/queue/item/18/"
    assert client.build_calls == [("folder/job/test", {"REF": "main"}, None)]
    assert status.build_number == 4
    assert status.status == "success"
    assert client.queue_calls == [18]
    assert client.info_calls == [("folder/job/test", 4)]


def test_confluence_adapter_uses_atlassian_sdk_v2_page_api(monkeypatch) -> None:
    client = FakeConfluence()
    constructor_calls: list[tuple[tuple, dict]] = []

    def confluence_constructor(*args, **kwargs):
        constructor_calls.append((args, kwargs))
        return client

    monkeypatch.setattr(adapters, "Confluence", confluence_constructor)
    adapter = ConfluenceAdapter("cloud id")

    page = adapter.get_page("secret", "42")
    updated = adapter.update_page(
        "secret",
        page,
        ConfluencePreset(page_id="42", title="Updated release notes"),
        "<p>New</p>",
    )

    assert constructor_calls == [
        (
            (),
            {
                "url": "https://api.atlassian.com/ex/confluence/cloud%20id",
                "token": "secret",
                "cloud": True,
                "api_root": "wiki/api",
                "api_version": "v2",
            },
        ),
        (
            (),
            {
                "url": "https://api.atlassian.com/ex/confluence/cloud%20id",
                "token": "secret",
                "cloud": True,
                "api_root": "wiki/api",
                "api_version": "v2",
            },
        ),
    ]
    assert client.get_calls == [("wiki/api/v2/pages/42", {"body-format": "storage"})]
    assert client.put_calls == [
        (
            "wiki/api/v2/pages/42",
            {
                "id": "42",
                "status": "current",
                "title": "Updated release notes",
                "body": {"representation": "storage", "value": "<p>New</p>"},
                "version": {"number": 4},
            },
        )
    ]
    assert updated.version == 4


def test_sdk_permission_error_is_stable_and_token_safe() -> None:
    class FailingJira:
        def resource_url(self, *args, **kwargs):
            return "rest/api/3/issue"

        def get(self, *args, **kwargs):
            raise ApiPermissionError("token=secret")

    with pytest.raises(PermissionDeniedError) as raised:
        JiraAdapter("cloud", lambda token: FailingJira()).read_issue("secret", "DEV-1", {})

    assert "secret" not in str(raised.value)


class _FakeHttpResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (409, ConflictError),
        (429, NetworkError),
    ],
)
def test_sdk_http_status_maps_to_a_stable_error_category(status_code, expected_error) -> None:
    class FailingJira:
        def resource_url(self, *args, **kwargs):
            return "rest/api/3/issue"

        def get(self, *args, **kwargs):
            raise RequestException(f"token=secret status={status_code}", response=_FakeHttpResponse(status_code))

    with pytest.raises(expected_error) as raised:
        JiraAdapter("cloud", lambda token: FailingJira()).read_issue("secret", "DEV-1", {})

    assert "secret" not in str(raised.value)


class _FakeHttpResponseWithBody(_FakeHttpResponse):
    def __init__(self, status_code: int, body: object) -> None:
        super().__init__(status_code)
        self._body = body

    def json(self):
        return self._body


def test_sdk_error_surfaces_jiras_own_error_messages_from_the_response_body() -> None:
    class FailingJira:
        def resource_url(self, *args, **kwargs):
            return "rest/api/3/issue"

        def get(self, *args, **kwargs):
            body = {"errorMessages": ["Issue does not exist or you do not have permission to see it."], "errors": {}}
            raise RequestException("not found", response=_FakeHttpResponseWithBody(404, body))

    with pytest.raises(InputValidationError) as raised:
        JiraAdapter("cloud", lambda token: FailingJira()).read_issue("secret", "DEV-99999", {})

    assert "Issue does not exist" in str(raised.value)


def test_sdk_error_surfaces_field_level_errors_and_still_redacts_secrets() -> None:
    class FailingJira:
        def resource_url(self, *args, **kwargs):
            return "rest/api/3/issue"

        def post(self, *args, **kwargs):
            body = {"errorMessages": [], "errors": {"summary": "token=secret-value the field exceeds 255 characters"}}
            raise RequestException("bad request", response=_FakeHttpResponseWithBody(400, body))

    with pytest.raises(InputValidationError) as raised:
        JiraAdapter("cloud", lambda token: FailingJira()).create_issue("secret", {"fields": {}})

    message = str(raised.value)
    assert "summary: " in message
    assert "exceeds 255 characters" in message
    assert "secret-value" not in message


def test_sdk_error_without_a_parsable_body_keeps_the_generic_message() -> None:
    class FailingJira:
        def resource_url(self, *args, **kwargs):
            return "rest/api/3/issue"

        def get(self, *args, **kwargs):
            raise RequestException("bad request", response=_FakeHttpResponse(400))

    with pytest.raises(InputValidationError) as raised:
        JiraAdapter("cloud", lambda token: FailingJira()).read_issue("secret", "DEV-1", {})

    assert str(raised.value) == "Remote service rejected the request (400)."


def test_sdk_timeout_without_a_response_falls_back_to_a_generic_network_error() -> None:
    """A timeout carries no HTTP status, so the outcome is inherently unclear; it must fail safe."""

    class FailingJenkins:
        def build_job(self, *args, **kwargs):
            raise Timeout("Read timed out while using token=secret")

    settings = JenkinsSettings(url="https://jenkins.test", username="jenkins-user")
    preset = JenkinsPreset(job="folder/job/test", allowed_parameters=["REF"])

    with pytest.raises(NetworkError) as raised:
        JenkinsAdapter(settings, lambda token: FailingJenkins()).run_build("secret", "test", preset, {})

    assert "secret" not in str(raised.value)
    assert "timed out" not in str(raised.value).lower()
