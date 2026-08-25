"""Policy-bearing workflows that sit between the CLI and secret-bearing broker."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from .config import require_preset, require_real_value
from .confirmation import confirm_mutation
from .errors import ConfigurationError, InputValidationError, VerificationError
from .markdown import markdown_to_storage
from .models import (
    BuildResult,
    ConfluencePreset,
    PageResult,
    PreviewResult,
    ProjectConfig,
    PullRequestResult,
    VerificationResult,
)
from .redaction import redact_text


class OperationClient(Protocol):
    def invoke(self, operation: str, payload: Mapping[str, Any]) -> dict[str, Any]: ...


class ProcessRunner(Protocol):
    def run(self, command: str, *, cwd: Path) -> subprocess.CompletedProcess[str]: ...


class ShellProcessRunner:
    def run(self, command: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
        # Commands are maintained by the target project, not derived from user input.
        return subprocess.run(  # noqa: S602
            command,
            shell=True,
            cwd=cwd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )


class VerificationRunner:
    def __init__(self, config: ProjectConfig, project_root: Path, runner: ProcessRunner | None = None) -> None:
        self.config = config
        self.project_root = project_root
        self.runner = runner or ShellProcessRunner()

    def run(self) -> list[VerificationResult]:
        project = self.config.project
        recipe_command = os.environ.get("JUST_DEV_PROJECT_VERIFY_COMMAND")
        if recipe_command:
            if "JUST_DEV_REPLACE_ME" in recipe_command:
                raise ConfigurationError(
                    "Project verification is still the starter hook. Replace JUST_DEV_REPLACE_ME "
                    "in scripts/devtools/recipes/project.just first."
                )
            commands = [recipe_command]
        elif project.starter_hook or not project.verify_commands:
            raise ConfigurationError(
                "Project verification is still the starter hook. Run it through just or configure "
                "direct-CLI verification commands."
            )
        else:
            commands = project.verify_commands
        results: list[VerificationResult] = []
        for command in commands:
            completed = self.runner.run(command, cwd=self.project_root)
            result = VerificationResult(
                command=command,
                returncode=completed.returncode,
                output=redact_text(completed.stdout or ""),
            )
            results.append(result)
            if completed.returncode != 0:
                raise VerificationError(f"Project verification failed: {command} (exit {completed.returncode}).")
        return results


def current_git_branch(project_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputValidationError("Could not determine the current Git branch.") from exc
    branch = completed.stdout.strip()
    if not branch or branch == "HEAD":
        raise InputValidationError("Cannot create a pull request from a detached HEAD.")
    return branch


def parse_parameters(values: Sequence[str]) -> dict[str, str]:
    parameters: dict[str, str] = {}
    for value in values:
        key, separator, parameter_value = value.partition("=")
        if not separator or not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise InputValidationError(f"Invalid build parameter '{value}'. Use KEY=VALUE.")
        if key in parameters:
            raise InputValidationError(f"Build parameter '{key}' was supplied more than once.")
        parameters[key] = parameter_value
    return parameters


class DevtoolsService:
    def __init__(
        self,
        config: ProjectConfig,
        project_root: Path,
        broker: OperationClient,
        *,
        verification_runner: VerificationRunner | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.broker = broker
        self.verification_runner = verification_runner or VerificationRunner(config, project_root)

    def _payload(self, **values: Any) -> dict[str, Any]:
        return {"config": self.config.model_dump(mode="json"), **values}

    def _validate_atlassian(self) -> None:
        require_real_value(self.config.atlassian.cloud_id, "atlassian.cloud_id")

    def _validate_bitbucket(self) -> None:
        for label, value in (
            ("bitbucket.workspace", self.config.bitbucket.workspace),
            ("bitbucket.repository", self.config.bitbucket.repository),
            ("bitbucket.username", self.config.bitbucket.username),
        ):
            require_real_value(value, label)

    def _validate_jenkins(self) -> None:
        require_real_value(self.config.jenkins.url, "jenkins.url")
        require_real_value(self.config.jenkins.username, "jenkins.username")

    def _validate_confluence_preset(self, preset: ConfluencePreset) -> None:
        require_real_value(preset.page_id, "confluence page_id")
        require_real_value(preset.title, "confluence title")

    def check_devtools(self) -> PreviewResult:
        problems: list[str] = []
        hook_path = self.project_root / "scripts" / "devtools" / "recipes" / "project.just"
        try:
            if "JUST_DEV_REPLACE_ME" in hook_path.read_text(encoding="utf-8"):
                problems.append("recipes/project.just still contains JUST_DEV_REPLACE_ME")
        except OSError:
            problems.append("recipes/project.just is missing")
        just = shutil.which("just")
        if just is None:
            problems.append("just >= 1.55 is required but just is not installed")
        else:
            try:
                version_output = subprocess.check_output(
                    [just, "--version"], text=True, stderr=subprocess.STDOUT
                ).strip()
                match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", version_output)
                if not match or tuple(int(part or 0) for part in match.groups()) < (1, 55, 0):
                    problems.append(f"just >= 1.55 is required (found: {version_output})")
            except (OSError, subprocess.CalledProcessError):
                problems.append("could not determine the installed just version")
        if problems:
            raise ConfigurationError("Devtools check failed: " + "; ".join(problems) + ".")
        return PreviewResult(action="check-devtools", details={"status": "ok"})

    @staticmethod
    def _jira_issue_id_or_key(value: str) -> str:
        if not value.strip():
            raise InputValidationError("Issue ID or key must not be empty.")
        return value.strip()

    _JIRA_PRESET_MANAGED_FIELDS = frozenset({"project", "issuetype", "labels", "components"})

    @classmethod
    def _jira_custom_fields(cls, value: Mapping[str, Any] | None) -> dict[str, Any]:
        fields = dict(value or {})
        managed = sorted(cls._JIRA_PRESET_MANAGED_FIELDS & fields.keys())
        if managed:
            raise InputValidationError(
                f"Field(s) {', '.join(managed)} come from the Jira preset and cannot be set directly."
            )
        return fields

    def create_jira_issue(
        self,
        preset_name: str,
        summary: str,
        *,
        description: str | None = None,
        fields: Mapping[str, Any] | None = None,
        dry_run: bool = False,
        yes: bool = False,
        announce: Callable[[PreviewResult], None] | None = None,
    ) -> dict[str, Any] | PreviewResult:
        self._validate_atlassian()
        require_preset(self.config.jira.presets, preset_name, "Jira")
        if not summary.strip():
            raise InputValidationError("Jira summary must not be empty.")
        extra_fields = self._jira_custom_fields(fields)
        preview = PreviewResult(
            action="create Jira issue",
            details={"preset": preset_name, "summary": summary, "description": description, "fields": extra_fields},
        )
        if dry_run:
            return preview
        if announce:
            announce(preview)
        confirm_mutation("create the Jira issue", yes=yes)
        return self.broker.invoke(
            "jira.create_issue",
            self._payload(preset=preset_name, summary=summary, description=description, fields=extra_fields),
        )

    def read_jira_issue(
        self,
        issue_id_or_key: str,
        *,
        fields: str | None = None,
        expand: str | None = None,
        properties: str | None = None,
    ) -> dict[str, Any]:
        self._validate_atlassian()
        parameters = {
            key: value for key, value in (("fields", fields), ("expand", expand), ("properties", properties)) if value
        }
        return self.broker.invoke(
            "jira.read_issue",
            self._payload(issue_id_or_key=self._jira_issue_id_or_key(issue_id_or_key), parameters=parameters),
        )

    def update_jira_issue(
        self,
        issue_id_or_key: str,
        *,
        summary: str | None = None,
        description: str | None = None,
        fields: Mapping[str, Any] | None = None,
        dry_run: bool = False,
        yes: bool = False,
        announce: Callable[[PreviewResult], None] | None = None,
    ) -> dict[str, Any] | PreviewResult:
        self._validate_atlassian()
        key = self._jira_issue_id_or_key(issue_id_or_key)
        extra = dict(fields or {})
        if summary is None and description is None and not extra:
            raise InputValidationError("Provide a summary, a description, or a JSON request body to update.")
        preview = PreviewResult(
            action="update Jira issue",
            details={"issue_id_or_key": key, "summary": summary, "description": description, "request": extra},
        )
        if dry_run:
            return preview
        if announce:
            announce(preview)
        confirm_mutation("update the Jira issue", yes=yes)
        return self.broker.invoke(
            "jira.update_issue",
            self._payload(issue_id_or_key=key, summary=summary, description=description, request=extra),
        )

    def delete_jira_issue(
        self,
        issue_id_or_key: str,
        *,
        delete_subtasks: bool = False,
        dry_run: bool = False,
        yes: bool = False,
        announce: Callable[[PreviewResult], None] | None = None,
    ) -> dict[str, Any] | PreviewResult:
        self._validate_atlassian()
        key = self._jira_issue_id_or_key(issue_id_or_key)
        parameters = {"deleteSubtasks": True} if delete_subtasks else {}
        preview = PreviewResult(action="delete Jira issue", details={"issue_id_or_key": key, "parameters": parameters})
        if dry_run:
            return preview
        if announce:
            announce(preview)
        confirm_mutation("delete the Jira issue", yes=yes)
        return self.broker.invoke("jira.delete_issue", self._payload(issue_id_or_key=key, parameters=parameters))

    def create_pull_request(
        self,
        title: str,
        *,
        dry_run: bool = False,
        yes: bool = False,
        no_verify: bool = False,
        source_branch: str | None = None,
        announce: Callable[[PreviewResult], None] | None = None,
    ) -> PullRequestResult | PreviewResult:
        if not title.strip():
            raise InputValidationError("Pull request title must not be empty.")
        self._validate_bitbucket()
        branch = source_branch or current_git_branch(self.project_root)
        preview = PreviewResult(
            action="create Bitbucket pull request",
            details={
                "title": title,
                "source_branch": branch,
                "target_branch": self.config.bitbucket.target_branch,
                "no_verify": no_verify,
            },
        )
        if dry_run:
            return preview
        if announce:
            announce(preview)
        if not no_verify:
            self.verification_runner.run()
        confirm_mutation(
            "create the pull request" if not no_verify else "skip verification and create the pull request", yes=yes
        )
        result = self.broker.invoke("bitbucket.create_pull_request", self._payload(title=title, source_branch=branch))
        return PullRequestResult.model_validate(result)

    def show_pull_request(self, pull_request_id: str | None = None) -> PullRequestResult | PreviewResult:
        self._validate_bitbucket()
        if pull_request_id:
            return PullRequestResult.model_validate(
                self.broker.invoke("bitbucket.get_pull_request", self._payload(pull_request_id=pull_request_id))
            )
        branch = current_git_branch(self.project_root)
        result = self.broker.invoke("bitbucket.find_open_pull_request", self._payload(source_branch=branch))
        if not result.get("found"):
            return PreviewResult(
                action="show Bitbucket pull request", details={"source_branch": branch, "found": False}
            )
        return PullRequestResult.model_validate(result)

    def run_build(
        self,
        preset_name: str,
        *,
        parameters: Sequence[str] = (),
        dry_run: bool = False,
        yes: bool = False,
        announce: Callable[[PreviewResult], None] | None = None,
    ) -> BuildResult | PreviewResult:
        self._validate_jenkins()
        preset = require_preset(self.config.jenkins.presets, preset_name, "Jenkins")
        values = parse_parameters(parameters)
        disallowed = set(values) - set(preset.allowed_parameters)
        if disallowed:
            raise InputValidationError(
                f"Jenkins preset '{preset_name}' does not allow parameter(s): {', '.join(sorted(disallowed))}."
            )
        preview = PreviewResult(
            action="run Jenkins build", details={"preset": preset_name, "job": preset.job, "parameters": values}
        )
        if dry_run:
            return preview
        if announce:
            announce(preview)
        confirm_mutation("queue the Jenkins build", yes=yes)
        return BuildResult.model_validate(
            self.broker.invoke("jenkins.run_build", self._payload(preset=preset_name, parameters=values))
        )

    def show_build_status(self, preset_name: str, reference: str) -> BuildResult:
        self._validate_jenkins()
        require_preset(self.config.jenkins.presets, preset_name, "Jenkins")
        return BuildResult.model_validate(
            self.broker.invoke("jenkins.get_build_status", self._payload(preset=preset_name, reference=reference))
        )

    def _read_markdown(self, file: Path | str) -> str:
        path = Path(file)
        if not path.is_absolute():
            path = self.project_root / path
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise InputValidationError(f"Release-notes file was not found: {path}") from exc
        except UnicodeDecodeError as exc:
            raise InputValidationError(f"Release-notes file is not UTF-8 text: {path}") from exc
        except OSError as exc:
            raise InputValidationError(f"Unable to read release-notes file: {path}") from exc

    def preview_release_notes(self, file: Path | str, *, preset_name: str = "release-notes") -> PageResult:
        preset = require_preset(self.config.confluence.presets, preset_name, "Confluence")
        self._validate_confluence_preset(preset)
        storage = markdown_to_storage(self._read_markdown(file))
        return PageResult(page_id=preset.page_id, title=preset.title, body=storage)

    def publish_release_notes(
        self,
        file: Path | str,
        *,
        preset_name: str = "release-notes",
        dry_run: bool = False,
        yes: bool = False,
        announce: Callable[[PageResult], None] | None = None,
    ) -> PageResult | PreviewResult:
        self._validate_atlassian()
        preview = self.preview_release_notes(file, preset_name=preset_name)
        if dry_run:
            return PreviewResult(
                action="publish Confluence release notes",
                details={"page_id": preview.page_id, "title": preview.title, "storage": preview.body or ""},
            )
        # Read once for a human-facing preview. The broker reads again immediately before its versioned write.
        current = PageResult.model_validate(
            self.broker.invoke("confluence.get_page", self._payload(page_id=preview.page_id))
        )
        if announce:
            announce(
                PageResult(
                    page_id=current.page_id,
                    title=preview.title,
                    version=current.version,
                    url=current.url,
                    body=preview.body,
                )
            )
        confirm_mutation("publish the Confluence release notes", yes=yes)
        result = self.broker.invoke(
            "confluence.update_page",
            self._payload(preset=preset_name, storage=preview.body or ""),
        )
        return PageResult.model_validate(result)

    def verify_project(self) -> list[VerificationResult]:
        return self.verification_runner.run()

    def run_ci(self) -> list[VerificationResult]:
        self.check_devtools()
        return self.verify_project()
