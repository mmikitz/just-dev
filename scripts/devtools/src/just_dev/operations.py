"""The broker's allowlisted operation dispatcher; raw tokens never leave it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .adapters import BitbucketAdapter, ConfluenceAdapter, JenkinsAdapter, JiraAdapter
from .atlassian import site_url_from_configured_cloud_id
from .config import require_preset
from .errors import AuthenticationError, ConfigurationError, InputValidationError
from .models import JiraPreset, ProjectConfig
from .redaction import redact_text


def _token(tokens: Mapping[str, str], scope: str, *, ci: bool = False) -> str:
    token = tokens.get(scope)
    if not token:
        if ci:
            raise AuthenticationError(
                f"CI requires the {scope} token credential JUST_DEV_CI_{scope.upper()}_TOKEN. "
                "Inject it from the CI credentials store."
            )
        raise AuthenticationError(
            f"No {scope} token is available in the unlocked profile. Add it with "
            f"`just configure-auth --entry {scope}=KEEPASS_ENTRY_UUID` and then run "
            "`just unlock-secrets`."
        )
    return token


def _config(payload: Mapping[str, Any]) -> ProjectConfig:
    value = payload.get("config")
    if not isinstance(value, Mapping):
        raise InputValidationError("Broker operation did not include a valid project configuration.")
    return ProjectConfig.model_validate(value)


def _request_object(payload: Mapping[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InputValidationError(f"Broker operation did not include valid Jira {name}.")
    return dict(value)


def _jira_adf_document(text: str) -> dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


def _jira_preset_fields(preset: JiraPreset) -> dict[str, Any]:
    fields: dict[str, Any] = {"project": {"key": preset.project}, "issuetype": {"name": preset.issue_type}}
    if preset.labels:
        fields["labels"] = list(preset.labels)
    if preset.components:
        fields["components"] = [{"name": name} for name in preset.components]
    return fields


def _jira_create_body(preset: JiraPreset, payload: Mapping[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = dict(_request_object(payload, "fields"))
    fields.update(_jira_preset_fields(preset))  # preset-governed keys always win over caller-supplied overrides
    fields["summary"] = str(payload["summary"])
    description = payload.get("description")
    if description:
        fields["description"] = _jira_adf_document(str(description))
    return {"fields": fields}


def _jira_update_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(_request_object(payload, "request"))
    fields = dict(body.get("fields") or {})
    summary = payload.get("summary")
    if summary:
        fields["summary"] = str(summary)
    description = payload.get("description")
    if description:
        fields["description"] = _jira_adf_document(str(description))
    labels = payload.get("labels")
    if labels:
        fields["labels"] = [label.strip() for label in str(labels).split(",") if label.strip()]
    priority = payload.get("priority")
    if priority:
        fields["priority"] = {"name": str(priority).strip()}
    if fields:
        body["fields"] = fields
    return body


def execute_operation(tokens: Mapping[str, str], operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute only a named, finite set of safe integration operations."""

    try:
        ci = payload.get("__just_dev_ci") is True
        config = _config(payload)
        if operation.startswith(("jira.", "confluence.")) and site_url_from_configured_cloud_id(
            config.atlassian.cloud_id
        ):
            raise ConfigurationError(
                "Credential broker received an unresolved Atlassian site URL. Run the operation through the CLI "
                "so its Cloud ID can be resolved first."
            )
        result: Any
        if operation == "jira.create_issue":
            jira_preset = require_preset(config.jira.presets, str(payload["preset"]), "Jira")
            result = JiraAdapter(config.atlassian.cloud_id).create_issue(
                _token(tokens, "jira", ci=ci), _jira_create_body(jira_preset, payload)
            )
        elif operation == "jira.read_issue":
            result = JiraAdapter(config.atlassian.cloud_id).read_issue(
                _token(tokens, "jira", ci=ci),
                str(payload["issue_id_or_key"]),
                _request_object(payload, "parameters"),
            )
        elif operation == "jira.search_issues":
            result = JiraAdapter(config.atlassian.cloud_id).search_issues(
                _token(tokens, "jira", ci=ci),
                _request_object(payload, "parameters"),
            )
        elif operation == "jira.update_issue":
            result = JiraAdapter(config.atlassian.cloud_id).update_issue(
                _token(tokens, "jira", ci=ci),
                str(payload["issue_id_or_key"]),
                _jira_update_body(payload),
            )
        elif operation == "jira.delete_issue":
            result = JiraAdapter(config.atlassian.cloud_id).delete_issue(
                _token(tokens, "jira", ci=ci),
                str(payload["issue_id_or_key"]),
                _request_object(payload, "parameters"),
            )
        elif operation == "jira.assign_issue":
            result = JiraAdapter(config.atlassian.cloud_id).assign_issue(
                _token(tokens, "jira", ci=ci),
                str(payload["issue_id_or_key"]),
                str(payload["assignee"]),
            )
        elif operation == "jira.comment_issue":
            result = JiraAdapter(config.atlassian.cloud_id).comment_issue(
                _token(tokens, "jira", ci=ci),
                str(payload["issue_id_or_key"]),
                {"body": _jira_adf_document(str(payload["comment"]))},
            )
        elif operation == "jira.attach_file":
            result = JiraAdapter(config.atlassian.cloud_id).attach_file(
                _token(tokens, "jira", ci=ci),
                str(payload["issue_id_or_key"]),
                str(payload["filename"]),
                str(payload["content_b64"]),
            )
        elif operation == "jira.list_transitions":
            result = JiraAdapter(config.atlassian.cloud_id).list_transitions(
                _token(tokens, "jira", ci=ci),
                str(payload["issue_id_or_key"]),
            )
        elif operation == "jira.transition_issue":
            result = JiraAdapter(config.atlassian.cloud_id).transition_issue(
                _token(tokens, "jira", ci=ci),
                str(payload["issue_id_or_key"]),
                str(payload["transition_id"]),
            )
        elif operation == "jira.verify_credentials":
            result = JiraAdapter(config.atlassian.cloud_id).verify_credentials(_token(tokens, "jira", ci=ci))
        elif operation == "bitbucket.create_pull_request":
            result = BitbucketAdapter(config.bitbucket).create_pull_request(
                _token(tokens, "bitbucket", ci=ci),
                str(payload["title"]),
                str(payload["source_branch"]),
                description=(str(payload["description"]) if payload.get("description") else None),
                reviewers=[str(reviewer) for reviewer in (payload.get("reviewers") or [])],
                close_source_branch=bool(payload.get("close_source_branch")),
            )
        elif operation == "bitbucket.get_pull_request":
            result = BitbucketAdapter(config.bitbucket).get_pull_request(
                _token(tokens, "bitbucket", ci=ci), str(payload["pull_request_id"])
            )
        elif operation == "bitbucket.find_open_pull_request":
            found = BitbucketAdapter(config.bitbucket).find_open_pull_request(
                _token(tokens, "bitbucket", ci=ci), str(payload["source_branch"])
            )
            if found is None:
                return {"found": False}
            return {"found": True, **found.model_dump(mode="json")}
        elif operation == "bitbucket.approve_pull_request":
            result = BitbucketAdapter(config.bitbucket).approve_pull_request(
                _token(tokens, "bitbucket", ci=ci), str(payload["pull_request_id"])
            )
        elif operation == "bitbucket.merge_pull_request":
            result = BitbucketAdapter(config.bitbucket).merge_pull_request(
                _token(tokens, "bitbucket", ci=ci),
                str(payload["pull_request_id"]),
                message=str(payload["message"]),
                merge_strategy=str(payload["merge_strategy"]),
                close_source_branch=bool(payload.get("close_source_branch")),
            )
        elif operation == "bitbucket.decline_pull_request":
            result = BitbucketAdapter(config.bitbucket).decline_pull_request(
                _token(tokens, "bitbucket", ci=ci), str(payload["pull_request_id"])
            )
        elif operation == "bitbucket.add_pull_request_comment":
            result = BitbucketAdapter(config.bitbucket).add_pull_request_comment(
                _token(tokens, "bitbucket", ci=ci), str(payload["pull_request_id"]), str(payload["comment"])
            )
        elif operation == "bitbucket.add_pull_request_reviewer":
            result = BitbucketAdapter(config.bitbucket).add_pull_request_reviewer(
                _token(tokens, "bitbucket", ci=ci), str(payload["pull_request_id"]), str(payload["reviewer"])
            )
        elif operation == "jenkins.run_build":
            preset_name = str(payload["preset"])
            jenkins_preset = require_preset(config.jenkins.presets, preset_name, "Jenkins")
            parameters = payload.get("parameters") or {}
            result = JenkinsAdapter(config.jenkins).run_build(
                _token(tokens, "jenkins", ci=ci),
                preset_name,
                jenkins_preset,
                {str(k): str(v) for k, v in parameters.items()},
            )
        elif operation == "jenkins.get_build_status":
            preset_name = str(payload["preset"])
            jenkins_preset = require_preset(config.jenkins.presets, preset_name, "Jenkins")
            result = JenkinsAdapter(config.jenkins).get_build_status(
                _token(tokens, "jenkins", ci=ci), preset_name, jenkins_preset, str(payload["reference"])
            )
        elif operation == "confluence.get_page":
            result = ConfluenceAdapter(config.atlassian.cloud_id).get_page(
                _token(tokens, "confluence", ci=ci), str(payload["page_id"])
            )
        elif operation == "confluence.update_page":
            preset_name = str(payload["preset"])
            confluence_preset = require_preset(config.confluence.presets, preset_name, "Confluence")
            current = ConfluenceAdapter(config.atlassian.cloud_id).get_page(
                _token(tokens, "confluence", ci=ci), confluence_preset.page_id
            )
            result = ConfluenceAdapter(config.atlassian.cloud_id).update_page(
                _token(tokens, "confluence", ci=ci), current, confluence_preset, str(payload["storage"])
            )
        else:
            raise InputValidationError(f"Broker operation '{operation}' is not allowed.")
        if isinstance(result, Mapping):
            return dict(result)
        return result.model_dump(mode="json")
    except Exception as exc:
        # This dispatcher also runs in CI, where there is no broker wrapper to redact remote diagnostics.
        if hasattr(exc, "message"):
            exc.message = redact_text(exc.message, list(tokens.values()))
        raise
