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

from .atlassian import resolve_site_cloud_id
from .broker import REQUIRED_SCOPES, BrokerManager, CloudIdCache, KeePassProfile, ProfileStore, validate_profile
from .config import load_project_config, project_root_from_environment
from .errors import AuthenticationError, DevtoolsError, InputValidationError
from .introspect import describe_commands as _describe_commands
from .jira import (
    parse_includes,
    prepare_attach_view,
    prepare_issue_view,
    prepare_search_view,
    render_attach_markdown,
    render_issue_markdown,
    render_search_markdown,
    validate_view,
)
from .models import BrokerStatus, PreviewResult
from .operations import execute_operation
from .redaction import redact_data, redact_text
from .rendering import filter_safe_output, known_safe_output_formats, render_markdown, render_text
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

_CI_SCOPES = ("jira", "confluence", "bitbucket", "jenkins")


def _ci_enabled() -> bool:
    return os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}


def _ci_configured_scopes() -> list[str]:
    """Scopes with a CI credential token set, mirroring `_CiOperationClient`'s lookup."""

    return sorted(scope for scope in _CI_SCOPES if os.environ.get(f"JUST_DEV_CI_{scope.upper()}_TOKEN", ""))


@dataclass
class Runtime:
    config_path: Path | None
    output_format: str | None
    project_root: Path
    safe: bool = False

    def config(self):
        return load_project_config(self.config_path, project_root=self.project_root)

    def resolve_local_cloud_id(
        self,
        profile: str,
        *,
        refresh: bool = False,
        required: bool = True,
    ) -> str | None:
        config = self.config()
        return CloudIdCache().resolve(
            config.atlassian.cloud_id,
            profile=profile,
            refresh=refresh,
            required=required,
        )

    def service(self, profile: str = "default", *, require_broker: bool = True) -> DevtoolsService:
        config = self.config()
        cloud_id_resolver: Callable[[str], str | None] | None
        if not require_broker:
            broker: Any = _NoBroker()
            cloud_id_resolver = None
        elif _ci_enabled():
            broker = _CiOperationClient()
            cloud_id_resolver = resolve_site_cloud_id
        else:
            broker = _LazyBroker(profile)

            def resolve_local_cloud_id(configured: str) -> str | None:
                del configured
                return self.resolve_local_cloud_id(profile, required=True)

            cloud_id_resolver = resolve_local_cloud_id
        return DevtoolsService(config, self.project_root, broker, cloud_id_resolver=cloud_id_resolver)


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
        tokens = {scope: os.environ.get(f"JUST_DEV_CI_{scope.upper()}_TOKEN", "") for scope in _CI_SCOPES}
        try:
            return execute_operation(tokens, operation, {**payload, "__just_dev_ci": True})
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
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Omit structural identity, URL, and attachment fields.")] = False,
) -> None:
    selected_format = output_format or os.environ.get("JUST_DEV_FORMAT") or None
    if selected_format is not None and selected_format not in known_safe_output_formats():
        raise typer.BadParameter("must be 'text', 'markdown', or 'json'", param_hint="--format")
    safe = safe or _flag_or_environment(False, "JUST_DEV_SAFE")
    context.obj = Runtime(
        config_path=config,
        output_format=selected_format,
        project_root=project_root_from_environment(),
        safe=safe,
    )


def _runtime(context: typer.Context) -> Runtime:
    value = context.obj
    if not isinstance(value, Runtime):
        raise RuntimeError("CLI runtime was not initialized.")
    return value


def _set_command_output_options(context: typer.Context, output_format: str | None, safe: bool) -> None:
    """Allow passthrough recipes to place output flags after their subcommand."""

    runtime = _runtime(context)
    if output_format is not None:
        if output_format not in known_safe_output_formats():
            raise InputValidationError("--format must be 'text', 'markdown', or 'json'.")
        runtime.output_format = output_format
    runtime.safe = runtime.safe or safe


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


def _emit(
    context: typer.Context,
    value: Any,
    *,
    default_format: str = "text",
    markdown_renderer: Callable[[Any], str] | None = None,
    err: bool = False,
) -> None:
    runtime = _runtime(context)
    data = redact_data(_serialize(value))
    if runtime.safe:
        data = filter_safe_output(data)
    output_format = runtime.output_format or default_format
    if output_format == "json":
        typer.echo(json.dumps(data, ensure_ascii=False, sort_keys=True), err=err)
    elif output_format == "markdown":
        typer.echo(markdown_renderer(data) if markdown_renderer else render_markdown(data), err=err)
    else:
        typer.echo(render_text(data), err=err)


def _announce_preview(context: typer.Context, preview: Any) -> None:
    """A mutation's preview is progress commentary, not its result (principle 20):
    it always goes to stderr, in the same bare shape `--dry-run` returns as the
    result, so `--format json` stdout carries exactly one JSON document (F1, F2)."""

    _emit(context, preview, err=True)


def _execute(
    context: typer.Context,
    action: Callable[[], Any],
    *,
    default_format: str = "text",
    markdown_renderer: Callable[[Any], str] | None = None,
) -> None:
    try:
        _emit(context, action(), default_format=default_format, markdown_renderer=markdown_renderer)
    except DevtoolsError as error:
        runtime = _runtime(context)
        message = redact_text(error)
        if (runtime.output_format or default_format) == "json":
            payload = {"error": {"code": error.exit_code, "kind": error.kind, "message": message}}
            typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True), err=True)
        else:
            typer.echo(f"error: {message}", err=True)
        raise typer.Exit(code=error.exit_code) from error


def _explicit_yes(yes: bool) -> bool:
    """Unlike every other mutation flag, --yes never has an environment
    counterpart: consent must be a real argument on the command line, not an
    ambient setting one `export` can apply to every mutation for a whole
    session (F6, principle 23). A lingering JUST_DEV_YES no longer waives
    anything; it only earns a warning before the mutation fails closed the
    same way an unconfirmed one always has (ConfirmationError, exit 26)."""

    if yes:
        return True
    if _flag_or_environment(False, "JUST_DEV_YES"):
        typer.echo("warning: JUST_DEV_YES no longer waives confirmation; pass --yes", err=True)
    return False


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


def _optional_int_or_environment(value: int | None, environment_name: str, label: str) -> int | None:
    """The int-typed counterpart to `_optional_value_or_environment`: empty means unset."""

    if value is not None:
        return value
    raw = os.environ.get(environment_name)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise InputValidationError(f"{label} must be an integer.") from exc


def _parse_entries(entries: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for entry in entries:
        scope, separator, uuid = entry.partition("=")
        scope = scope.strip().lower()
        if not separator or not scope or not uuid.strip() or scope in parsed:
            raise InputValidationError("Each --entry must be unique and use SCOPE=KEEPASS_ENTRY_UUID.")
        if scope not in REQUIRED_SCOPES:
            raise InputValidationError("--entry scope must be one of: " + ", ".join(sorted(REQUIRED_SCOPES)) + ".")
        parsed[scope] = uuid.strip()
    return parsed


def _parse_removed_entries(entries: list[str]) -> set[str]:
    removed = {entry.strip().lower() for entry in entries}
    if not all(removed) or len(removed) != len(entries):
        raise InputValidationError("Each --remove-entry scope must be non-empty and unique.")
    unknown = removed - REQUIRED_SCOPES
    if unknown:
        raise InputValidationError("--remove-entry scope must be one of: " + ", ".join(sorted(REQUIRED_SCOPES)) + ".")
    return removed


@app.command("check-devtools")
def check_devtools(
    context: typer.Context,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Validate prerequisites and ensure the project-specific hook was customized."""

    _set_command_output_options(context, output_format, safe)
    _execute(context, lambda: _runtime(context).service(require_broker=False).check_devtools())


@app.command("describe-commands")
def describe_commands(
    context: typer.Context,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """List every command as an MCP-shaped tool descriptor: name, description,
    inputSchema, outputSchema (where stable), and readOnly/destructive/idempotent
    annotations — the machine-readable manifest `just --list` does not provide (F4)."""

    _set_command_output_options(context, output_format, safe)
    _execute(context, lambda: {"tools": _describe_commands(app)}, default_format="json")


@auth_app.command("configure-auth")
def configure_auth(
    context: typer.Context,
    database: Annotated[Path | None, typer.Option("--database", help="Path to the KeePass .kdbx database.")] = None,
    keyfile: Annotated[Path | None, typer.Option("--keyfile", help="Optional KeePass keyfile.")] = None,
    clear_keyfile: Annotated[
        bool, typer.Option("--clear-keyfile", help="Remove the configured KeePass keyfile.")
    ] = False,
    entry: Annotated[
        list[str] | None, typer.Option("--entry", help="Repeat: jira|confluence|bitbucket|jenkins=entry UUID.")
    ] = None,
    remove_entry: Annotated[
        list[str] | None, typer.Option("--remove-entry", help="Repeat: remove a configured scope entry.")
    ] = None,
    profile: Annotated[str, typer.Option("--profile", help="Local profile name.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Incrementally store local paths, entry UUIDs, and non-secret Cloud-ID cache data."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")

    def action() -> PreviewResult:
        if keyfile is not None and clear_keyfile:
            raise InputValidationError("Use either --keyfile or --clear-keyfile, not both.")
        store = ProfileStore()
        existing = store.load(profile) if store.path_for(profile).is_file() else None
        chosen_database = database or (
            Path(existing.database) if existing else Path(typer.prompt("KeePass database path"))
        )
        if clear_keyfile:
            chosen_keyfile: str | None = None
        elif keyfile is not None:
            chosen_keyfile = str(keyfile.expanduser())
        else:
            chosen_keyfile = existing.keyfile if existing else None
        entries = dict(existing.entries) if existing else {}
        parsed_entries = _parse_entries(entry or [])
        removed_entries = _parse_removed_entries(remove_entry or [])
        if set(parsed_entries) & removed_entries:
            raise InputValidationError("A scope cannot be supplied to both --entry and --remove-entry.")
        entries.update(parsed_entries)
        for scope in removed_entries:
            entries.pop(scope, None)
        value = KeePassProfile(
            database=str(chosen_database.expanduser()),
            keyfile=chosen_keyfile,
            entries=entries,
            cloud_ids=existing.cloud_ids if existing else {},
        )
        validate_profile(value)
        path = store.save(profile, value)
        try:
            # configure-auth is the explicit refresh point. A cached good value is
            # retained when tenant metadata is temporarily unavailable.
            _runtime(context).resolve_local_cloud_id(profile, refresh=True, required=False)
        except DevtoolsError as exc:
            typer.echo(f"warning: Cloud-ID cache was not refreshed: {redact_text(exc)}", err=True)
        return PreviewResult(
            action="configure auth profile",
            details={"profile": profile, "path": str(path), "configured_scopes": sorted(entries)},
        )

    _execute(context, action)


@auth_app.command("unlock-secrets")
def unlock_secrets(
    context: typer.Context,
    profile: Annotated[str, typer.Option("--profile", help="Local profile name.")] = "default",
    ttl_hours: Annotated[float, typer.Option("--ttl-hours", help="Session lifetime, at most 8 hours.")] = 8,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Prompt for the KeePass master password and start the local broker."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")

    def action() -> Any:
        if not 0 < ttl_hours <= 8:
            raise InputValidationError("--ttl-hours must be greater than 0 and no more than 8.")
        # A missing mapping must not prevent a partial broker from unlocking
        # Bitbucket or Jenkins. The Jira/Confluence call itself gives the
        # actionable failure if its mapping remains unavailable.
        ProfileStore().load(profile)
        try:
            _runtime(context).resolve_local_cloud_id(profile, required=False)
        except DevtoolsError as exc:
            typer.echo(f"warning: Cloud-ID cache was not checked: {redact_text(exc)}", err=True)
        return BrokerManager().unlock_from_keepass(profile, ttl_seconds=int(ttl_hours * 3600))

    _execute(context, action)


@auth_app.command("show-auth-status")
def show_auth_status(
    context: typer.Context,
    profile: Annotated[str, typer.Option("--profile", help="Local profile name.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Show whether the local credential broker is unlocked for a profile."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")

    def action() -> BrokerStatus:
        if _ci_enabled():
            # CI never uses the local KeePass broker; report on the env-var tokens it
            # actually authenticates with instead of a broker session that doesn't exist.
            return BrokerStatus(active=bool(_ci_configured_scopes()), source="ci")
        return BrokerManager().status(profile)

    _execute(context, action)


@auth_app.command("lock-secrets")
def lock_secrets(
    context: typer.Context,
    profile: Annotated[str, typer.Option("--profile", help="Local profile name.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Lock the local credential broker, ending its unlocked session."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
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
    extra_fields: Annotated[
        str | None,
        typer.Option("--extra-fields", help="Optional JSON object merged into 'fields', e.g. for custom fields."),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Create a new Jira issue from a configured preset."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .create_jira_issue(
                _argument_or_environment(preset, "JUST_DEV_JIRA_PRESET", "Jira preset"),
                _argument_or_environment(summary, "JUST_DEV_JIRA_SUMMARY", "Jira summary"),
                description=_optional_value_or_environment(description, "JUST_DEV_JIRA_DESCRIPTION"),
                fields=_json_object_or_environment(extra_fields, "JUST_DEV_JIRA_EXTRA_FIELDS", "Jira extra fields"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@jira_app.command("read-jira-issue")
def read_jira_issue(
    context: typer.Context,
    issue_id_or_key: Annotated[str | None, typer.Argument(help="Issue ID or key, e.g. ABC-123.")] = None,
    fields: Annotated[
        str | None, typer.Option("--fields", help="Comma-separated field list, e.g. 'summary,status'.")
    ] = None,
    include: Annotated[
        str | None, typer.Option("--include", help="Comma-separated optional sections: links, attachments, comments.")
    ] = None,
    view: Annotated[str, typer.Option("--view", help="Issue view: summary or full.")] = "summary",
    expand: Annotated[
        str | None, typer.Option("--expand", help="Comma-separated entities to expand, e.g. 'changelog'.")
    ] = None,
    properties: Annotated[
        str | None, typer.Option("--properties", help="Comma-separated entity property keys to return.")
    ] = None,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Fetch a single Jira issue by ID or key."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")

    def action() -> dict[str, Any]:
        resolved_fields = _optional_value_or_environment(fields, "JUST_DEV_JIRA_READ_FIELDS")
        resolved_include = _optional_value_or_environment(include, "JUST_DEV_JIRA_READ_INCLUDE")
        resolved_view = _option_or_environment(view, "JUST_DEV_JIRA_READ_VIEW", "summary")
        selected_includes = parse_includes(resolved_include)
        resolved_view = validate_view(resolved_view)
        result = (
            _runtime(context)
            .service(profile)
            .read_jira_issue(
                _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
                fields=resolved_fields,
                include=selected_includes,
                view=resolved_view,
                expand=_optional_value_or_environment(expand, "JUST_DEV_JIRA_READ_EXPAND"),
                properties=_optional_value_or_environment(properties, "JUST_DEV_JIRA_READ_PROPERTIES"),
            )
        )
        return prepare_issue_view(
            result,
            fields=resolved_fields,
            includes=selected_includes,
            view=resolved_view,
        )

    _execute(
        context,
        action,
        default_format="markdown",
        markdown_renderer=render_issue_markdown,
    )


@jira_app.command("search-jira-issues")
def search_jira_issues(
    context: typer.Context,
    jql: Annotated[str | None, typer.Argument(help="JQL query, e.g. 'project = DEV AND status = Open'.")] = None,
    fields: Annotated[
        str | None, typer.Option("--fields", help="Comma-separated field list, e.g. 'summary,status'.")
    ] = None,
    view: Annotated[str, typer.Option("--view", help="Issue view: summary or full.")] = "summary",
    limit: Annotated[int | None, typer.Option("--limit", help="Maximum number of issues to return (1-100).")] = None,
    next_page_token: Annotated[
        str | None, typer.Option("--next-page-token", help="Pagination token from a previous search response.")
    ] = None,
    expand: Annotated[
        str | None, typer.Option("--expand", help="Comma-separated entities to expand, e.g. 'changelog'.")
    ] = None,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Search Jira issues by JQL, paginated via --next-page-token."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")

    def action() -> dict[str, Any]:
        resolved_fields = _optional_value_or_environment(fields, "JUST_DEV_JIRA_SEARCH_FIELDS")
        resolved_view = _option_or_environment(view, "JUST_DEV_JIRA_SEARCH_VIEW", "summary")
        resolved_view = validate_view(resolved_view)
        resolved_limit = _optional_int_or_environment(limit, "JUST_DEV_JIRA_SEARCH_LIMIT", "--limit")
        result = (
            _runtime(context)
            .service(profile)
            .search_jira_issues(
                _argument_or_environment(jql, "JUST_DEV_JIRA_SEARCH_JQL", "JQL query"),
                fields=resolved_fields,
                view=resolved_view,
                limit=resolved_limit,
                next_page_token=_optional_value_or_environment(next_page_token, "JUST_DEV_JIRA_SEARCH_NEXT_PAGE_TOKEN"),
                expand=_optional_value_or_environment(expand, "JUST_DEV_JIRA_SEARCH_EXPAND"),
            )
        )
        return prepare_search_view(result, fields=resolved_fields, view=resolved_view)

    _execute(
        context,
        action,
        default_format="markdown",
        markdown_renderer=render_search_markdown,
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
    labels: Annotated[str | None, typer.Option("--labels", help="Comma-separated labels; replaces all labels.")] = None,
    priority: Annotated[str | None, typer.Option("--priority", help="New priority name, e.g. High.")] = None,
    request: Annotated[
        str | None,
        typer.Argument(
            help="Optional JSON object merged into the Edit issue request, e.g. custom fields or update operations."
        ),
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Update a Jira issue's summary, description, labels, priority, or other fields."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .update_jira_issue(
                _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
                summary=_optional_value_or_environment(summary, "JUST_DEV_JIRA_SUMMARY"),
                description=_optional_value_or_environment(description, "JUST_DEV_JIRA_DESCRIPTION"),
                labels=_optional_value_or_environment(labels, "JUST_DEV_JIRA_LABELS"),
                priority=_optional_value_or_environment(priority, "JUST_DEV_JIRA_PRIORITY"),
                fields=_json_object_or_environment(request, "JUST_DEV_JIRA_UPDATE_REQUEST", "Jira update request"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@jira_app.command("assign-jira-issue")
def assign_jira_issue(
    context: typer.Context,
    issue_id_or_key: Annotated[str | None, typer.Argument(help="Issue ID or key, e.g. ABC-123.")] = None,
    assignee: Annotated[
        str | None, typer.Option("--assignee", help="Assignee's Jira account ID, or their email address.")
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Assign a Jira issue to a user by account ID or email."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .assign_jira_issue(
                _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
                _argument_or_environment(assignee, "JUST_DEV_JIRA_ASSIGNEE", "Assignee account ID or email"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@jira_app.command("comment-jira-issue")
def comment_jira_issue(
    context: typer.Context,
    issue_id_or_key: Annotated[str | None, typer.Argument(help="Issue ID or key, e.g. ABC-123.")] = None,
    comment: Annotated[str | None, typer.Argument(help="Comment text, sent as Atlassian Document Format.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Add a comment to a Jira issue."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .comment_jira_issue(
                _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
                _argument_or_environment(comment, "JUST_DEV_JIRA_COMMENT", "Comment"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@jira_app.command("attach-jira-issue")
def attach_jira_issue(
    context: typer.Context,
    issue_id_or_key: Annotated[str | None, typer.Argument(help="Issue ID or key, e.g. ABC-123.")] = None,
    file_path: Annotated[str | None, typer.Argument(help="Path to the local file to attach.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Attach a local file to a Jira issue."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")

    def action() -> dict[str, Any] | PreviewResult:
        result = (
            _runtime(context)
            .service(profile)
            .attach_jira_issue(
                _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
                _argument_or_environment(file_path, "JUST_DEV_JIRA_FILE_PATH", "File path"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        )
        return prepare_attach_view(result) if isinstance(result, dict) else result

    _execute(
        context,
        action,
        default_format="markdown",
        markdown_renderer=render_attach_markdown,
    )


@jira_app.command("transition-jira-issue")
def transition_jira_issue(
    context: typer.Context,
    issue_id_or_key: Annotated[str | None, typer.Argument(help="Issue ID or key, e.g. ABC-123.")] = None,
    status: Annotated[str | None, typer.Argument(help="Target status name, e.g. 'Done'.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Move a Jira issue to a named workflow status."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .transition_jira_issue(
                _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
                _argument_or_environment(status, "JUST_DEV_JIRA_STATUS", "Target status"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
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
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Delete a Jira issue, optionally with its subtasks."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .delete_jira_issue(
                _argument_or_environment(issue_id_or_key, "JUST_DEV_JIRA_ISSUE_ID_OR_KEY", "Issue ID or key"),
                delete_subtasks=_flag_or_environment(delete_subtasks, "JUST_DEV_JIRA_DELETE_SUBTASKS"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@bitbucket_app.command("create-pull-request")
def create_pull_request(
    context: typer.Context,
    title: Annotated[str | None, typer.Argument(help="Pull request title.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Pull request description.")] = None,
    reviewer: Annotated[list[str] | None, typer.Option("--reviewer", help="Reviewer username; repeatable.")] = None,
    close_source_branch: Annotated[
        bool, typer.Option("--close-source-branch", help="Close the source branch after merge.")
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    no_verify: Annotated[
        bool, typer.Option("--no-verify", help="Skip project verification after explicit confirmation.")
    ] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Create a new Bitbucket pull request from the current branch."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .create_pull_request(
                _argument_or_environment(title, "JUST_DEV_PR_TITLE", "Pull request title"),
                description=_optional_value_or_environment(description, "JUST_DEV_PR_DESCRIPTION"),
                reviewer=reviewer
                or ([os.environ["JUST_DEV_PR_REVIEWER"]] if os.environ.get("JUST_DEV_PR_REVIEWER") else []),
                close_source_branch=_flag_or_environment(close_source_branch, "JUST_DEV_PR_CLOSE_SOURCE_BRANCH"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                no_verify=_flag_or_environment(no_verify, "JUST_DEV_NO_VERIFY"),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@bitbucket_app.command("show-pull-request")
def show_pull_request(
    context: typer.Context,
    pull_request_id: Annotated[str | None, typer.Argument(help="Optional pull request ID.")] = None,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Show a Bitbucket pull request by ID, or the current branch's open one."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    value = pull_request_id if pull_request_id is not None else os.environ.get("JUST_DEV_PR_ID") or None
    _execute(context, lambda: _runtime(context).service(profile).show_pull_request(value))


@bitbucket_app.command("approve-pull-request")
def approve_pull_request(
    context: typer.Context,
    pull_request_id: Annotated[str | None, typer.Argument(help="Pull request ID.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Approve a Bitbucket pull request."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .approve_pull_request(
                _argument_or_environment(pull_request_id, "JUST_DEV_PR_ID", "Pull request ID"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@bitbucket_app.command("decline-pull-request")
def decline_pull_request(
    context: typer.Context,
    pull_request_id: Annotated[str | None, typer.Argument(help="Pull request ID.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Decline a Bitbucket pull request."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .decline_pull_request(
                _argument_or_environment(pull_request_id, "JUST_DEV_PR_ID", "Pull request ID"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@bitbucket_app.command("comment-pull-request")
def comment_pull_request(
    context: typer.Context,
    pull_request_id: Annotated[str | None, typer.Argument(help="Pull request ID.")] = None,
    comment: Annotated[str | None, typer.Argument(help="Comment text.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Add a comment to a Bitbucket pull request."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .comment_pull_request(
                _argument_or_environment(pull_request_id, "JUST_DEV_PR_ID", "Pull request ID"),
                _argument_or_environment(comment, "JUST_DEV_PR_COMMENT", "Comment"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@bitbucket_app.command("add-pull-request-reviewer")
def add_pull_request_reviewer(
    context: typer.Context,
    pull_request_id: Annotated[str | None, typer.Argument(help="Pull request ID.")] = None,
    reviewer: Annotated[str | None, typer.Argument(help="Reviewer username.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Add a reviewer to a Bitbucket pull request."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .add_pull_request_reviewer(
                _argument_or_environment(pull_request_id, "JUST_DEV_PR_ID", "Pull request ID"),
                _argument_or_environment(reviewer, "JUST_DEV_PR_REVIEWER_NAME", "Reviewer"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@bitbucket_app.command("merge-pull-request")
def merge_pull_request(
    context: typer.Context,
    pull_request_id: Annotated[str | None, typer.Argument(help="Pull request ID.")] = None,
    message: Annotated[
        str | None, typer.Option("--message", help="Merge commit message; defaults to a generated one.")
    ] = None,
    merge_strategy: Annotated[
        str, typer.Option("--merge-strategy", help="One of: merge_commit, squash, fast_forward.")
    ] = "merge_commit",
    close_source_branch: Annotated[
        bool, typer.Option("--close-source-branch", help="Close the source branch after merge.")
    ] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Merge a Bitbucket pull request."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .merge_pull_request(
                _argument_or_environment(pull_request_id, "JUST_DEV_PR_ID", "Pull request ID"),
                message=_optional_value_or_environment(message, "JUST_DEV_PR_MESSAGE"),
                merge_strategy=_option_or_environment(merge_strategy, "JUST_DEV_PR_MERGE_STRATEGY", "merge_commit"),
                close_source_branch=_flag_or_environment(close_source_branch, "JUST_DEV_PR_CLOSE_SOURCE_BRANCH"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@jenkins_app.command("run-build")
def run_build(
    context: typer.Context,
    preset: Annotated[str | None, typer.Argument(help="Named Jenkins preset.")] = None,
    parameter: Annotated[
        list[str] | None, typer.Option("--parameter", "-p", help="Allowed KEY=VALUE parameter; repeatable.")
    ] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show the request without writing.")] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the interactive confirmation.")] = False,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Queue a Jenkins build from a named preset."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .run_build(
                _argument_or_environment(preset, "JUST_DEV_BUILD_PRESET", "Jenkins preset"),
                parameters=parameter
                or ([os.environ["JUST_DEV_BUILD_PARAMETER"]] if os.environ.get("JUST_DEV_BUILD_PARAMETER") else []),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda preview: _announce_preview(context, preview),
            )
        ),
    )


@jenkins_app.command("show-build-status")
def show_build_status(
    context: typer.Context,
    preset: Annotated[str | None, typer.Argument(help="Named Jenkins preset.")] = None,
    reference: Annotated[str | None, typer.Argument(help="Queue/build reference.")] = None,
    profile: Annotated[str, typer.Option("--profile", help="Local auth profile.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Show a Jenkins build's status by preset and reference."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(profile)
            .show_build_status(
                _argument_or_environment(preset, "JUST_DEV_BUILD_PRESET", "Jenkins preset"),
                _argument_or_environment(reference, "JUST_DEV_BUILD_REFERENCE", "Build reference"),
            )
        ),
    )


@confluence_app.command("preview-release-notes")
def preview_release_notes(
    context: typer.Context,
    file: Annotated[Path | None, typer.Argument(help="Markdown file.")] = None,
    preset: Annotated[str, typer.Option("--preset", help="Named Confluence page preset.")] = "release-notes",
    profile: Annotated[str, typer.Option("--profile", help="Unused for preview; retained for symmetry.")] = "default",
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Render a markdown file as Confluence storage format without publishing."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")
    del profile
    _execute(
        context,
        lambda: (
            _runtime(context)
            .service(require_broker=False)
            .preview_release_notes(
                _argument_or_environment(
                    str(file) if file else None, "JUST_DEV_RELEASE_NOTES_FILE", "Release-notes file"
                ),
                preset_name=_option_or_environment(preset, "JUST_DEV_CONFLUENCE_PRESET", "release-notes"),
            )
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
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Publish a markdown file as Confluence release notes."""

    _set_command_output_options(context, output_format, safe)
    profile = _option_or_environment(profile, "JUST_DEV_PROFILE", "default")

    def action() -> Any:
        path = _argument_or_environment(
            str(file) if file else None, "JUST_DEV_RELEASE_NOTES_FILE", "Release-notes file"
        )
        return (
            _runtime(context)
            .service(profile)
            .publish_release_notes(
                path,
                preset_name=_option_or_environment(preset, "JUST_DEV_CONFLUENCE_PRESET", "release-notes"),
                dry_run=_flag_or_environment(dry_run, "JUST_DEV_DRY_RUN"),
                yes=_explicit_yes(yes),
                announce=lambda page: _announce_preview(context, page),
            )
        )

    _execute(context, action)


@project_app.command("verify-project")
def verify_project(
    context: typer.Context,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Run the project's configured verification command."""

    _set_command_output_options(context, output_format, safe)
    _execute(context, lambda: _runtime(context).service(require_broker=False).verify_project())


@project_app.command("run-ci")
def run_ci(
    context: typer.Context,
    output_format: Annotated[
        str | None, typer.Option("--format", help="Output format: text, markdown, or json.")
    ] = None,
    safe: Annotated[bool, typer.Option("--safe", help="Filter structural identity and URL fields.")] = False,
) -> None:
    """Validate devtools prerequisites, then run the project's verification command."""

    _set_command_output_options(context, output_format, safe)
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
