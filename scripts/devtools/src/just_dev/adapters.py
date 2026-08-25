"""Small, SDK-backed gateways for the supported remote services."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, Protocol, TypeVar
from urllib.parse import quote

import jenkins
from atlassian import Bitbucket, Confluence, Jira
from atlassian.errors import ApiConflictError, ApiPermissionError
from requests.exceptions import RequestException

from .errors import (
    AuthenticationError,
    ConflictError,
    DevtoolsError,
    InputValidationError,
    NetworkError,
    PermissionDeniedError,
)
from .models import (
    BitbucketSettings,
    BuildResult,
    ConfluencePreset,
    JenkinsPreset,
    JenkinsSettings,
    PageResult,
    PullRequestResult,
)


class JiraClient(Protocol):
    def resource_url(self, resource: str, api_root: str | None = None, api_version: str | None = None) -> str: ...

    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any: ...

    def post(self, path: str, *, data: Mapping[str, Any] | None = None, params: Mapping[str, Any] | None = None) -> Any: ...

    def put(self, path: str, *, data: Mapping[str, Any] | None = None, params: Mapping[str, Any] | None = None) -> Any: ...

    def delete(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any: ...


class BitbucketClient(Protocol):
    def get_pull_requests(
        self,
        project_key: str,
        repository_slug: str,
        state: str = "OPEN",
        order: str = "newest",
        limit: int = 100,
        start: int = 0,
        at: str | None = None,
    ) -> Any: ...

    def create_pull_request(self, project_key: str, repository_slug: str, data: Mapping[str, Any]) -> Any: ...

    def get_pull_request(self, project_key: str, repository_slug: str, pull_request_id: str | int) -> Any: ...


class ConfluenceClient(Protocol):
    def resource_url(self, resource: str, api_root: str | None = None, api_version: str | None = None) -> str: ...

    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any: ...

    def put(self, path: str, *, data: Mapping[str, Any] | None = None) -> Any: ...


class JenkinsClient(Protocol):
    def build_job(self, name: str, parameters: Mapping[str, str] | None = None, token: str | None = None) -> int: ...

    def get_queue_item(self, number: int, depth: int = 0) -> Any: ...

    def get_build_info(self, name: str, number: int, depth: int = 0) -> Any: ...


_T = TypeVar("_T")
_JENKINS_STATUS = re.compile(r"\[(\d{3})\]")


def _atlassian_gateway(product: str, cloud_id: str) -> str:
    return f"https://api.atlassian.com/ex/{product}/{quote(cloud_id, safe='')}"


def _bitbucket_service_url(api_base: str) -> str:
    """Convert the configured v2 API URL to the SDK's service-root URL."""

    base = api_base.rstrip("/")
    return base[:-4] if base.endswith("/2.0") else base


def _mapping(value: Any, service: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NetworkError(f"{service} returned an unexpected response.")
    return value


def _nested_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _exception_status(error: Exception) -> int | None:
    """Extract an HTTP status when one is available without exposing its body."""

    for candidate in (error, getattr(error, "reason", None)):
        response = getattr(candidate, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
    match = _JENKINS_STATUS.search(str(error))
    return int(match.group(1)) if match else None


def _sdk_error(service: str, error: Exception) -> DevtoolsError:
    status = _exception_status(error)
    if status == 401:
        return AuthenticationError("Remote service rejected the configured credentials.")
    if status == 403:
        return PermissionDeniedError("The token is not authorized for this operation.")
    if status == 409:
        return ConflictError("The remote resource changed; refresh and try again.")
    if status == 429:
        return NetworkError("Remote service rate limit reached; retry later.")
    if status is not None and 400 <= status < 500:
        return InputValidationError(f"Remote service rejected the request ({status}).")
    if status is not None:
        return NetworkError(f"{service} request failed with HTTP {status}.")
    if isinstance(error, ApiPermissionError):
        return PermissionDeniedError("The token is not authorized for this operation.")
    if isinstance(error, ApiConflictError):
        return ConflictError("The remote resource changed; refresh and try again.")
    if isinstance(error, jenkins.NotFoundException):
        return InputValidationError("Remote service rejected the request (404).")
    return NetworkError(f"{service} request failed.")


def _sdk_errors(service: str) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
    """Decorate a public adapter method so the two SDKs' exceptions become stable, token-safe errors."""

    def decorator(method: Callable[..., _T]) -> Callable[..., _T]:
        @wraps(method)
        def wrapper(*args: Any, **kwargs: Any) -> _T:
            try:
                return method(*args, **kwargs)
            except DevtoolsError:
                raise
            except (
                ApiConflictError,
                ApiPermissionError,
                RequestException,
                jenkins.JenkinsException,
                OSError,
            ) as exc:
                raise _sdk_error(service, exc) from exc

        return wrapper

    return decorator


class JiraAdapter:
    def __init__(self, cloud_id: str, client_factory: Callable[[str], JiraClient] | None = None) -> None:
        self.base_url = _atlassian_gateway("jira", cloud_id)
        self._client_factory = client_factory or self._new_client

    def _new_client(self, token: str) -> JiraClient:
        return Jira(url=self.base_url, token=token, cloud=True, api_version="3")

    def _client(self, token: str) -> JiraClient:
        return self._client_factory(token)

    @staticmethod
    def _issue_path(client: JiraClient, issue_id_or_key: str) -> str:
        return f"{client.resource_url('issue')}/{quote(issue_id_or_key, safe='-')}"

    @staticmethod
    def _completed_response(value: Any, fallback: Mapping[str, Any]) -> dict[str, Any]:
        if value is None or value is True:
            return dict(fallback)
        return dict(_mapping(value, "Jira"))

    @_sdk_errors("Jira")
    def create_issue(self, token: str, request: Mapping[str, Any]) -> dict[str, Any]:
        client = self._client(token)
        body = dict(request)
        update_history = body.pop("updateHistory", None)
        params = {"updateHistory": update_history} if update_history is not None else None
        return dict(_mapping(client.post(client.resource_url("issue"), data=body, params=params), "Jira"))

    @_sdk_errors("Jira")
    def read_issue(self, token: str, issue_id_or_key: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
        client = self._client(token)
        return dict(
            _mapping(
                client.get(self._issue_path(client, issue_id_or_key), params=dict(parameters) or None),
                "Jira",
            )
        )

    @_sdk_errors("Jira")
    def update_issue(self, token: str, issue_id_or_key: str, request: Mapping[str, Any]) -> dict[str, Any]:
        client = self._client(token)
        body = dict(request)
        query_keys = (
            "notifyUsers",
            "overrideScreenSecurity",
            "overrideEditableFlag",
            "returnIssue",
            "expand",
        )
        params = {key: body.pop(key) for key in query_keys if key in body}
        response = client.put(self._issue_path(client, issue_id_or_key), data=body, params=params or None)
        return self._completed_response(response, {"issue_id_or_key": issue_id_or_key, "updated": True})

    @_sdk_errors("Jira")
    def delete_issue(self, token: str, issue_id_or_key: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
        client = self._client(token)
        response = client.delete(self._issue_path(client, issue_id_or_key), params=dict(parameters) or None)
        return self._completed_response(response, {"issue_id_or_key": issue_id_or_key, "deleted": True})


class BitbucketAdapter:
    def __init__(self, settings: BitbucketSettings, client_factory: Callable[[str], BitbucketClient] | None = None) -> None:
        self.settings = settings
        self._client_factory = client_factory or self._new_client

    def _new_client(self, token: str) -> BitbucketClient:
        client = Bitbucket(
            url=_bitbucket_service_url(self.settings.api_base),
            username=self.settings.username,
            password=token,
            cloud=True,
        )
        # The SDK only recognizes api.bitbucket.org when inferring this setting.
        # Keep configured proxy endpoints on the Bitbucket Cloud v2 API as well.
        client.api_root = ""
        client.api_version = "2.0"
        return client

    def _client(self, token: str) -> BitbucketClient:
        return self._client_factory(token)

    def _repository(self) -> tuple[str, str]:
        return (
            quote(self.settings.workspace, safe=""),
            quote(self.settings.repository, safe=""),
        )

    @staticmethod
    def _as_result(data: Mapping[str, Any], *, existing: bool = False) -> PullRequestResult:
        source = _nested_mapping(_nested_mapping(data.get("source")).get("branch")).get("name", "")
        target = _nested_mapping(_nested_mapping(data.get("destination")).get("branch")).get("name", "")
        links = _nested_mapping(data.get("links"))
        html_link = _nested_mapping(links.get("html"))
        return PullRequestResult(
            id=data.get("id", ""),
            title=str(data.get("title", "")),
            source_branch=str(source),
            target_branch=str(target),
            url=html_link.get("href"),
            existing=existing,
        )

    def _find_open_pull_request(self, client: BitbucketClient, source_branch: str) -> PullRequestResult | None:
        workspace, repository = self._repository()
        for value in client.get_pull_requests(workspace, repository, state="OPEN", limit=50):
            item = _mapping(value, "Bitbucket")
            source = _nested_mapping(_nested_mapping(item.get("source")).get("branch")).get("name")
            if source == source_branch:
                return self._as_result(item, existing=True)
        return None

    @_sdk_errors("Bitbucket")
    def find_open_pull_request(self, token: str, source_branch: str) -> PullRequestResult | None:
        return self._find_open_pull_request(self._client(token), source_branch)

    @_sdk_errors("Bitbucket")
    def create_pull_request(self, token: str, title: str, source_branch: str) -> PullRequestResult:
        client = self._client(token)
        existing = self._find_open_pull_request(client, source_branch)
        if existing:
            return existing
        workspace, repository = self._repository()
        payload: dict[str, Any] = {
            "title": title,
            "source": {"branch": {"name": source_branch}},
            "destination": {"branch": {"name": self.settings.target_branch}},
            "close_source_branch": False,
        }
        if self.settings.reviewers:
            payload["reviewers"] = [{"username": reviewer} for reviewer in self.settings.reviewers]
        data = _mapping(client.create_pull_request(workspace, repository, payload), "Bitbucket")
        return self._as_result(data)

    @_sdk_errors("Bitbucket")
    def get_pull_request(self, token: str, pull_request_id: str | int) -> PullRequestResult:
        workspace, repository = self._repository()
        data = _mapping(
            self._client(token).get_pull_request(workspace, repository, quote(str(pull_request_id), safe="")),
            "Bitbucket",
        )
        return self._as_result(data)


class JenkinsAdapter:
    def __init__(self, settings: JenkinsSettings, client_factory: Callable[[str], JenkinsClient] | None = None) -> None:
        self.settings = settings
        self.base_url = settings.url.rstrip("/")
        self._client_factory = client_factory or self._new_client

    def _new_client(self, token: str) -> JenkinsClient:
        return jenkins.Jenkins(self.base_url, username=self.settings.username, password=token, timeout=30)

    def _client(self, token: str) -> JenkinsClient:
        return self._client_factory(token)

    @_sdk_errors("Jenkins")
    def run_build(self, token: str, preset_name: str, preset: JenkinsPreset, parameters: Mapping[str, str]) -> BuildResult:
        queue_id = self._client(token).build_job(preset.job, parameters=dict(parameters))
        if not isinstance(queue_id, int):
            raise NetworkError("Jenkins did not return a queue ID.")
        return BuildResult(
            preset=preset_name,
            queue_id=queue_id,
            status="queued",
            url=f"{self.base_url}/queue/item/{queue_id}/",
        )

    @_sdk_errors("Jenkins")
    def get_build_status(self, token: str, preset_name: str, preset: JenkinsPreset, reference: str) -> BuildResult:
        if not reference.isdigit():
            raise InputValidationError("Build reference must be a numeric queue ID or build number.")
        queue_id = int(reference)
        client = self._client(token)
        queue = _mapping(client.get_queue_item(queue_id), "Jenkins")
        executable = _nested_mapping(queue.get("executable"))
        if executable.get("number") is not None:
            try:
                build_number = int(executable["number"])
            except (TypeError, ValueError) as exc:
                raise NetworkError("Jenkins returned an invalid build number.") from exc
            build = _mapping(client.get_build_info(preset.job, build_number), "Jenkins")
            return BuildResult(
                preset=preset_name,
                queue_id=queue_id,
                build_number=build_number,
                status="running" if build.get("building") else str(build.get("result") or "unknown").lower(),
                url=build.get("url"),
            )
        if queue.get("cancelled"):
            return BuildResult(preset=preset_name, queue_id=queue_id, status="cancelled", url=queue.get("url"))
        return BuildResult(preset=preset_name, queue_id=queue_id, status="queued", url=queue.get("url"))


class ConfluenceAdapter:
    def __init__(self, cloud_id: str, client_factory: Callable[[str], ConfluenceClient] | None = None) -> None:
        self.base_url = _atlassian_gateway("confluence", cloud_id)
        self._client_factory = client_factory or self._new_client

    def _new_client(self, token: str) -> ConfluenceClient:
        return Confluence(
            url=self.base_url,
            token=token,
            cloud=True,
            api_root="wiki/api",
            api_version="v2",
        )

    def _client(self, token: str) -> ConfluenceClient:
        return self._client_factory(token)

    @staticmethod
    def _as_page(data: Mapping[str, Any], *, body: str | None = None) -> PageResult:
        links = _nested_mapping(data.get("_links"))
        version = _nested_mapping(data.get("version"))
        return PageResult(
            page_id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            version=version.get("number"),
            url=links.get("webui") or data.get("url"),
            body=body,
        )

    @_sdk_errors("Confluence")
    def get_page(self, token: str, page_id: str) -> PageResult:
        client = self._client(token)
        data = _mapping(
            client.get(client.resource_url(f"pages/{quote(page_id, safe='')}"), params={"body-format": "storage"}),
            "Confluence",
        )
        body = _nested_mapping(_nested_mapping(data.get("body")).get("storage")).get("value")
        return self._as_page(data, body=body if isinstance(body, str) else None)

    @_sdk_errors("Confluence")
    def update_page(self, token: str, page: PageResult, preset: ConfluencePreset, storage: str) -> PageResult:
        if page.version is None:
            raise NetworkError("Confluence page response did not include a version.")
        client = self._client(token)
        payload = {
            "id": page.page_id,
            "status": "current",
            "title": preset.title,
            "body": {"representation": "storage", "value": storage},
            "version": {"number": page.version + 1},
        }
        data = _mapping(
            client.put(client.resource_url(f"pages/{quote(page.page_id, safe='')}"), data=payload),
            "Confluence",
        )
        return self._as_page(data, body=storage)
