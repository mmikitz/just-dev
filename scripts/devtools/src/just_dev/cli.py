"""Typer command line interface; recipes pass user data through JUST_DEV_* values."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel

from .broker import BrokerManager, KeePassProfile, ProfileStore, validate_profile
from .config import load_project_config, project_root_from_environment
from .errors import AuthenticationError, DevtoolsError, InputValidationError
from .operations import execute_operation
from .models import PreviewResult
from .redaction import redact_data, redact_text
from .workflows import DevtoolsService


app = typer.Typer(help="Portable, least-privilege developer workflows.", no_args_is_help=True)
auth_app = typer.Typer(help="Manage the local KeePass-backed credential broker.", no_args_is_help=True)
jira_app = typer.Typer(help="Jira operations.", no_args_is_help=True)
bitbucket_app = typer.Typer(help="Bitbucket operations.", no_args_is_help=True)
jenkins_app = typer.Typer(help="Jenkins operations.", no_args_is_help=True)
confluence_app = typer.Typer(help="Confluence operations.", no_args_is_help=True)
project_app = typer.Typer(help="Project verification operations.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(jira_app, name="jira")
app.add_typer(bitbucket_app, name="bitbucket")
app.add_typer(jenkins_app, name="jenkins")
app.add_typer(confluence_app, name="confluence")
app.add_typer(project_app, name="project")


@dataclass
class Runtime:
    config_path: Path | None
    output_format: str
    project_root: Path

    def service(self, profile: str = "default", *, require_broker: bool = True) -> DevtoolsService:
        config = load_project_config(self.config_path, project_root=self.project_root)
        if not require_broker:
            broker: Any = _NoBroker()
        elif os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}:
            broker = _CiOperationClient()
        else:
            broker = _LazyBroker(profile)
        return DevtoolsService(config, self.project_root, broker)


class _NoBroker:
    def invoke(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        del operation, payload
        raise AuthenticationError("This operation requires an active credential broker. Run unlock-secrets first.")


class _LazyBroker:
    """Delay local runtime setup and authentication until an operation actually needs it."""

    def __init__(self, profile: str) -> None:
        self.profile = profile

    def invoke(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        return BrokerManager().client(self.profile).invoke(operation, payload)


class _CiOperationClient:
    """CI-only execution with credentials injected by the job's credentials store."""

    def invoke(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        tokens = {
            scope: os.environ.get(f"JUST_DEV_CI_{scope.upper()}_TOKEN", "")
            for scope in ("jira", "confluence", "bitbucket", "jenkins")
        }
        try:
            return execute_operation(tokens, operation, payload)
        except DevtoolsError as error:
            error.message = redact_text(error.message, list(tokens.values()))
            raise
        except Exception as error:
            # There is no broker wrapper here to isolate raw diagnostics; redact before
            # this reaches typer's default traceback output, which would print it verbatim.
            raise DevtoolsError(redact_text(error, list(tokens.values()))) from None


@app.callback()
def callback(
    context: typer.Context,
    config: Annotated[Path | None, typer.Option("--config", help="Path to a secret-free project TOML file.")] = None,
    output_format: Annotated[str, typer.Option("--format", help="Output format: text or json.")] = "text",
) -> None:
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("must be 'text' or 'json'", param_hint="--format")
    context.obj = Runtime(config_path=config, output_format=output_format, project_root=project_root_from_environment())


def _runtime(context: typer.Context) -> Runtime:
    value = context.obj
    if not isinstance(value, Runtime):
        raise RuntimeError("CLI runtime was not initialized.")
    return value


def _serialize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return value


def _human(value: Any) -> str:
    data = _serialize(value)
    if isinstance(data, list):
        return "\n\n".join(_human(item) for item in data)
    if isinstance(data, dict):
        return "\n".join(f"{key}: {item}" for key, item in data.items())
    return str(data)


def _emit(context: typer.Context, value: Any) -> None:
    runtime = _runtime(context)
    safe = redact_data(_serialize(value))
    if runtime.output_format == "json":
        typer.echo(json.dumps(safe, ensure_ascii=False, sort_keys=True))
    else:
        typer.echo(_human(safe))


def _execute(context: typer.Context, action: Callable[[], Any]) -> None:
    try:
        _emit(context, action())
    except DevtoolsError as error:
        typer.echo(f"error: {redact_text(error)}", err=True)
        raise typer.Exit(code=error.exit_code) from error


def _argument_or_environment(value: str | None, environment_name: str, label: str) -> str:
    result = value if value is not None else os.environ.get(environment_name)
    if result is None or not result.strip():
        raise InputValidationError(f"{label} is required.")
    return result


def _flag_or_environment(value: bool, environment_name: str) -> bool:
    """Recipes encode flags as exported 1/empty values; direct CLI flags still win."""

    if value:
        return True
    raw = os.environ.get(environment_name, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _option_or_environment(value: str, environment_name: str, default: str) -> str:
    """Allow a recipe-exported optional argument without overriding an explicit CLI choice."""

    candidate = os.environ.get(environment_name)
    return candidate if value == default and candidate else value


def _json_object_or_environment(
    value: str | None,
    environment_name: str,
    label: str,
    *,
    required: bool = False,
) -> dict[str, Any]:
    """Load a JSON object from a CLI argument or its recipe-exported equivalent."""

    raw = value if value is not None else os.environ.get(environment_name)
    if raw is None or not raw.strip():
        if required:
            raise InputValidationError(f"{label} is required and must be a JSON object.")
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InputValidationError(f"{label} must be valid JSON: {exc.msg}.") from exc
    if not isinstance(parsed, dict):
        raise InputValidationError(f"{label} must be a JSON object.")
    return parsed


def _optional_value_or_environment(value: str | None, environment_name: str) -> str | None:
    """The optional-argument counterpart to `_argument_or_environment`: empty means unset."""

    result = value if value is not None else os.environ.get(environment_name)
    return result or None


def _parse_entries(entries: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for entry in entries:
        scope, separator, uuid = entry.partition("=")
        if not separator or not scope or not uuid or scope in parsed:
            raise InputValidationError("Each --entry must be unique and use SCOPE=KEEPASS_ENTRY_UUID.")
        parsed[scope] = uuid
    return parsed


@app.command("check-devtools")
def check_devtools(context: typer.Context) -> None:
    """Validate prerequisites and ensure the project-specific hook was customized."""

    _execute(context, lambda: _runtime(context).service(require_broker=False).check_devtools())


@auth_app.command("configure-auth")
def configure_auth(
    context: typer.Context,
    database: Annotated[Path | None, typer.Option("--database", help="Path to the KeePass .kdbx database.")] = None,
    keyfile: Annotated[Path | None, typer.Option("--keyfile", help="Optional KeePass keyfile.")] = None,
    entry: Annotated[list[str], typer.Option("--entry", help="Repeat: jira|confluence|bitbucket|jenkins=entry UUID.")] = [],
    profile: Annotated[str, typer.Option("--profile", help="Local profile name.")] = "default",
) -> None:
    """Store a local profile containing paths and entry UUIDs, never tokens."""

    def action() -> PreviewResult:
        chosen_database = database or Path(typer.prompt("KeePass database path"))
        parsed_entries = _parse_entries(entry)
        if not parsed_entries:
            parsed_entries = {
                scope: typer.prompt(f"KeePass entry UUID for {scope}")
                for scope in ("jira", "confluence", "bitbucket", "jenkins")
            }
        value = KeePassProfile(
            database=str(chosen_database.expanduser()),
            keyfile=str(keyfile.expanduser()) if keyfile else None,
            entries=parsed_entries,
        )
        validate_profile(value)
        path = ProfileStore().save(profile, value)
        return PreviewResult(action="configure auth profile", details={"profile": profile, "path": str(path)})

    _execute(context, action)


@auth_app.command("unlock-secrets")
def unlock_secrets(
    context: typer.Context,
    profile: Annotated[str, typer.Option("--profile", help="Local profile name.")] = "default",
    ttl_hours: Annotated[float, typer.Option("--ttl-hours", help="Session lifetime, at most 8 hours.")] = 8,
) -> None:
    """Prompt for the KeePass master password and start the local broker."""

    def action() -> Any:
        if not 0 < ttl_hours <= 8:
            raise InputValidationError("--ttl-hours must be greater than 0 and no more than 8.")
        return BrokerManager().unlock_from_keepass(profile, ttl_seconds=int(ttl_hours * 3600))

    _execute(context, action)


@auth_app.command("show-auth-status")
def show_auth_status(
    context: typer.Context,
    profile: Annotated[str, typer.Option("--profile", help="Local profile name.")] = "default",
) -> None:
    _execute(context, lambda: BrokerManager().status(profile))


@auth_app.command("lock-secrets")
def lock_secrets(
    context: typer.Context,
    profile: Annotated[str, typer.Option("--profile", help="Local profile name.")] = "default",
) -> None:
    _execute(context, lambda: BrokerManager().lock(profile))


@jira_app.command("create-jira-issue")
def create_jira_issue(
    context: typer.Context,
    preset: Annotated[
        str | None, typer.Argument(help="Named Jira preset (project, issue type, labels, components).")
    ] = None,
    summary: Annotated[str | None, typer.Argument(help="Issue summary.")] = None,
    description: Annotated[
        str | None, typer.Option("--description", help="Plain-text description, sent as Atlassian Document Format.")
    ] = None,
    fields: Annotated[
        str | None,
        typer.Option("--fields", help="Optional JSON object merged into 'fields', e.g. for custom fields."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
) -> None:
    _execute(
        context,
        lambda: _runtime(context).service(profile).create_jira_issue(
            _argument_or_environment(preset, "JUST_DEV_JIRA_PRESET", "Jira preset"),
            _argument_or_environment(summary, "JUST_DEV_JIRA_SUMMARY", "Jira summary"),
            description=_optional_value_or_environment(description, "JUST_DEV_JIRA_DESCRIPTION"),
            fields=_json_object_or_environment(fields, "JUST_DEV_JIRA_FIELDS", "Jira fields"),
            dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
            yes=_flag_or_environment(yes, "JUST_DEV_YES"),
            announce=lambda preview: _emit(context, {"preview": preview}),
        ),
    )


@jira_app.command("read-jira-isdue")
def read_jira_isdue(
    context: typer.Context,
    issue_id_or_key: Annotated[str | None, typer.Argument(help="Issue ID or key, e.g. ABC-123.")] = None,
    fields: Annotated[
        str | None, typer.Option("--fields", help="Comma-separated field list, e.g. 'summary,status'.")
    ] = None,
    expand: Annotated[
        str | None, typer.Option("--expand", help="Comma-separated entities to expand, e.g. 'changelog'.")
    ] = None,
    properties: Annotated[
        str | None, typer.Option("--properties", help="Comma-separated entity property keys to return.")
    ] = None,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
) -> None:
    _execute(
        context,
        lambda: _runtime(context).service(profile).read_jira_issue(
            _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
            fields=_optional_value_or_environment(fields, "JUST_DEV_JIRA_READ_FIELDS"),
            expand=_optional_value_or_environment(expand, "JUST_DEV_JIRA_READ_EXPAND"),
            properties=_optional_value_or_environment(properties, "JUST_DEV_JIRA_READ_PROPERTIES"),
        ),
    )


@jira_app.command("update-jira-issue")
def update_jira_issue(
    context: typer.Context,
    issue_id_or_key: Annotated[str | None, typer.Argument(help="Issue ID or key, e.g. ABC-123.")] = None,
    summary: Annotated[str | None, typer.Option("--summary", help="New summary.")] = None,
    description: Annotated[
        str | None,
        typer.Option("--description", help="New plain-text description, sent as Atlassian Document Format."),
    ] = None,
    request: Annotated[
        str | None,
        typer.Argument(
            help="Optional JSON object merged into the Edit issue request, e.g. custom fields or update operations."
        ),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
) -> None:
    _execute(
        context,
        lambda: _runtime(context).service(profile).update_jira_issue(
            _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
            summary=_optional_value_or_environment(summary, "JUST_DEV_JIRA_SUMMARY"),
            description=_optional_value_or_environment(description, "JUST_DEV_JIRA_DESCRIPTION"),
            fields=_json_object_or_environment(request, "JUST_DEV_JIRA_UPDATE_REQUEST", "Jira update request"),
            dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
            yes=_flag_or_environment(yes, "JUST_DEV_YES"),
            announce=lambda preview: _emit(context, {"preview": preview}),
        ),
    )


@jira_app.command("delete-jira-issue")
def delete_jira_issue(
    context: typer.Context,
    issue_id_or_key: Annotated[str | None, typer.Argument(help="Issue ID or key, e.g. ABC-123.")] = None,
    delete_subtasks: Annotated[
        bool, typer.Option("--delete-subtasks", help="Also delete subtasks of this issue.")
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
) -> None:
    _execute(
        context,
        lambda: _runtime(context).service(profile).delete_jira_issue(
            _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
            delete_subtasks=_flag_or_environment(delete_subtasks, "JUST_DEV_JIRA_DELETE_SUBTASKS"),
            dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
            yes=_flag_or_environment(yes, "JUST_DEV_YES"),
            announce=lambda preview: _emit(context, {"preview": preview}),
        ),
    )


@bitbucket_app.command("create-pull-request")
def create_pull_request(
    context: typer.Context,
    title: Annotated[str | None, typer.Argument(help="Pull request title.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    no_verify: Annotated[bool, typer.Option("--no-verify", help="Skip project verification after explicit confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
) -> None:
    _execute(
        context,
        lambda: _runtime(context).service(profile).create_pull_request(
            _argument_or_environment(title, "JUST_DEV_PR_TITLE", "Pull request title"),
            dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
            yes=_flag_or_environment(yes, "JUST_DEV_YES"),
            no_verify=_flag_or_environment(no_verify, "JUST_DEV_NO_VERIFY"),
            announce=lambda preview: _emit(context, {"preview": preview}),
        ),
    )


@bitbucket_app.command("show-pull-request")
def show_pull_request(
    context: typer.Context,
    pull_request_id: Annotated[str | None, typer.Argument(help="Optional pull request ID.")] = None,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
) -> None:
    value = pull_request_id if pull_request_id is not None else os.environ.get("JUST_DEV_PR_ID") or None
    _execute(context, lambda: _runtime(context).service(profile).show_pull_request(value))


@jenkins_app.command("run-build")
def run_build(
    context: typer.Context,
    preset: Annotated[str | None, typer.Argument(help="Named Jenkins preset.")] = None,
    parameter: Annotated[list[str], typer.Option("--parameter", "-p", help="Allowed KEY=VALUE parameter; repeatable.")] = [],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
) -> None:
    _execute(
        context,
        lambda: _runtime(context).service(profile).run_build(
            _argument_or_environment(preset, "JUST_DEV_BUILD_PRESET", "Jenkins preset"),
            parameters=parameter or ([os.environ["JUST_DEV_BUILD_PARAMETER"]] if os.environ.get("JUST_DEV_BUILD_PARAMETER") else []),
            dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
            yes=_flag_or_environment(yes, "JUST_DEV_YES"),
            announce=lambda preview: _emit(context, {"preview": preview}),
        ),
    )


@jenkins_app.command("show-build-status")
def show_build_status(
    context: typer.Context,
    preset: Annotated[str | None, typer.Argument(help="Named Jenkins preset.")] = None,
    reference: Annotated[str | None, typer.Argument(help="Queue/build reference.")] = None,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
) -> None:
    _execute(
        context,
        lambda: _runtime(context).service(profile).show_build_status(
            _argument_or_environment(preset, "JUST_DEV_BUILD_PRESET", "Jenkins preset"),
            _argument_or_environment(reference, "JUST_DEV_BUILD_REFERENCE", "Build reference"),
        ),
    )


@confluence_app.command("preview-release-notes")
def preview_release_notes(
    context: typer.Context,
    file: Annotated[Path | None, typer.Argument(help="Markdown file.")] = None,
    preset: Annotated[str, typer.Option("--preset", help="Named Confluence page preset.")] = "release-notes",
    profile: Annotated[str, typer.Option("--profile", help="Unused for preview; retained for symmetry.")] = "default",
) -> None:
    del profile
    _execute(
        context,
        lambda: _runtime(context).service(require_broker=False).preview_release_notes(
            _argument_or_environment(str(file) if file else None, "JUST_DEV_RELEASE_NOTES_FILE", "Release-notes file"),
            preset_name=_option_or_environment(preset, "JUST_DEV_CONFLUENCE_PRESET", "release-notes"),
        ),
    )


@confluence_app.command("publish-release-notes")
def publish_release_notes(
    context: typer.Context,
    file: Annotated[Path | None, typer.Argument(help="Markdown file.")] = None,
    preset: Annotated[str, typer.Option("--preset", help="Named Confluence page preset.")] = "release-notes",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
) -> None:
    def action() -> Any:
        path = _argument_or_environment(str(file) if file else None, "JUST_DEV_RELEASE_NOTES_FILE", "Release-notes file")
        return _runtime(context).service(profile).publish_release_notes(
            path,
            preset_name=_option_or_environment(preset, "JUST_DEV_CONFLUENCE_PRESET", "release-notes"),
            dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
            yes=_flag_or_environment(yes, "JUST_DEV_YES"),
            announce=lambda page: _emit(context, {"preview": page}),
        )

    _execute(context, action)


@project_app.command("verify-project")
def verify_project(context: typer.Context) -> None:
    _execute(context, lambda: _runtime(context).service(require_broker=False).verify_project())


@project_app.command("run-ci")
def run_ci(context: typer.Context) -> None:
    _execute(context, lambda: _runtime(context).service(require_broker=False).run_ci())


def main() -> None:
    try:
        app()
    except DevtoolsError as error:
        # Covers errors raised by callback/argument parsing before a command wrapper is active.
        typer.echo(f"error: {redact_text(error)}", err=True)
        raise SystemExit(error.exit_code) from error


if __name__ == "__main__":
    main()
