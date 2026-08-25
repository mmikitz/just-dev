"""The broker's allowlisted operation dispatcher; raw tokens never leave it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .adapters import BitbucketAdapter, ConfluenceAdapter, JenkinsAdapter, JiraAdapter
from .config import require_preset
from .errors import AuthenticationError, InputValidationError
from .models import JiraPreset, ProjectConfig
from .redaction import redact_text


def _token(tokens: Mapping[str, str], scope: str) -> str:
    token = tokens.get(scope)
    if not token:
        raise AuthenticationError(f"The unlocked KeePass profile has no {scope} token entry.")
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


def _jira_description_document(text: str) -> dict[str, Any]:
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


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
        fields["description"] = _jira_description_document(str(description))
    return {"fields": fields}


def _jira_update_body(payload: Mapping[str, Any]) -> dict[str, Any]:
    body = dict(_request_object(payload, "request"))
    fields = dict(body.get("fields") or {})
    summary = payload.get("summary")
    if summary:
        fields["summary"] = str(summary)
    description = payload.get("description")
    if description:
        fields["description"] = _jira_description_document(str(description))
    if fields:
        body["fields"] = fields
    return body


def execute_operation(tokens: Mapping[str, str], operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute only a named, finite set of safe integration operations."""

    try:
        config = _config(payload)
        if operation == "jira.create_issue":
            preset = require_preset(config.jira.presets, str(payload["preset"]), "Jira")
            result = JiraAdapter(config.atlassian.cloud_id).create_issue(
                _token(tokens, "jira"), _jira_create_body(preset, payload)
            )
        elif operation == "jira.read_issue":
            result = JiraAdapter(config.atlassian.cloud_id).read_issue(
                _token(tokens, "jira"),
                str(payload["issue_id_or_key"]),
                _request_object(payload, "parameters"),
            )
        elif operation == "jira.update_issue":
            result = JiraAdapter(config.atlassian.cloud_id).update_issue(
                _token(tokens, "jira"),
                str(payload["issue_id_or_key"]),
                _jira_update_body(payload),
            )
        elif operation == "jira.delete_issue":
            result = JiraAdapter(config.atlassian.cloud_id).delete_issue(
                _token(tokens, "jira"),
                str(payload["issue_id_or_key"]),
                _request_object(payload, "parameters"),
            )
        elif operation == "bitbucket.create_pull_request":
            result = BitbucketAdapter(config.bitbucket).create_pull_request(
                _token(tokens, "bitbucket"), str(payload["title"]), str(payload["source_branch"])
            )
        elif operation == "bitbucket.get_pull_request":
            result = BitbucketAdapter(config.bitbucket).get_pull_request(_token(tokens, "bitbucket"), str(payload["pull_request_id"]))
        elif operation == "bitbucket.find_open_pull_request":
            found = BitbucketAdapter(config.bitbucket).find_open_pull_request(
                _token(tokens, "bitbucket"), str(payload["source_branch"])
            )
            if found is None:
                return {"found": False}
            return {"found": True, **found.model_dump(mode="json")}
        elif operation == "jenkins.run_build":
            preset_name = str(payload["preset"])
            preset = require_preset(config.jenkins.presets, preset_name, "Jenkins")
            parameters = payload.get("parameters") or {}
            result = JenkinsAdapter(config.jenkins).run_build(
                _token(tokens, "jenkins"), preset_name, preset, {str(k): str(v) for k, v in parameters.items()}
            )
        elif operation == "jenkins.get_build_status":
            preset_name = str(payload["preset"])
            preset = require_preset(config.jenkins.presets, preset_name, "Jenkins")
            result = JenkinsAdapter(config.jenkins).get_build_status(
                _token(tokens, "jenkins"), preset_name, preset, str(payload["reference"])
            )
        elif operation == "confluence.get_page":
            result = ConfluenceAdapter(config.atlassian.cloud_id).get_page(_token(tokens, "confluence"), str(payload["page_id"]))
        elif operation == "confluence.update_page":
            preset_name = str(payload["preset"])
            preset = require_preset(config.confluence.presets, preset_name, "Confluence")
            current = ConfluenceAdapter(config.atlassian.cloud_id).get_page(_token(tokens, "confluence"), preset.page_id)
            result = ConfluenceAdapter(config.atlassian.cloud_id).update_page(
                _token(tokens, "confluence"), current, preset, str(payload["storage"]))
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
