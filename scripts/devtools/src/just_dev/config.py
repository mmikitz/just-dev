"""Project-local, secret-free configuration loading and validation."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError

from .errors import ConfigurationError
from .models import ProjectConfig

PLACEHOLDER_MARKERS = ("REPLACE", "example.invalid", "JUST_DEV_REPLACE_ME")


def project_root_from_environment() -> Path:
    """Find the root supplied by recipes, or sensibly fall back for direct CLI use."""

    explicit = os.environ.get("JUST_DEV_PROJECT_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()

    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "justfile").is_file():
            return candidate
    return current


def default_config_path(project_root: Path | None = None) -> Path:
    root = project_root or project_root_from_environment()
    return root / "scripts" / "devtools" / "config" / "project.toml"


def load_project_config(path: Path | str | None = None, *, project_root: Path | None = None) -> ProjectConfig:
    explicit_path = path is not None
    config_path = Path(path) if path else default_config_path(project_root)
    try:
        with config_path.open("rb") as config_file:
            raw = tomllib.load(config_file)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Project configuration was not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Invalid TOML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Unable to read project configuration: {exc}") from exc

    if not explicit_path:
        raw = _apply_test_overrides(raw)

    try:
        return ProjectConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid project configuration: {exc}") from exc


def _apply_test_overrides(raw: dict) -> dict:
    """Overlay TEST_CLOUD_ID / TEST_JIRA_PROJECT onto the default, checked-in config.

    Lets an isolated session (no local secrets store available) point the CLI at a
    personal Atlassian account for end-to-end testing, without ever writing real
    account values into the checked-in, secret-free project.toml. Only applies when
    loading the default config path: an explicit --config always wins untouched, so
    this can't shadow a config a caller (tests included) picked deliberately.
    """
    cloud_id = os.environ.get("TEST_CLOUD_ID")
    if cloud_id:
        raw.setdefault("atlassian", {})["cloud_id"] = cloud_id

    jira_project = os.environ.get("TEST_JIRA_PROJECT")
    if jira_project:
        for preset in raw.get("jira", {}).get("presets", {}).values():
            preset["project"] = jira_project

    return raw


def require_real_value(value: str, label: str) -> str:
    if not value.strip() or any(marker.lower() in value.lower() for marker in PLACEHOLDER_MARKERS):
        raise ConfigurationError(f"{label} is still a starter placeholder in config/project.toml.")
    return value


def require_preset[Preset](mapping: Mapping[str, Preset], name: str, label: str) -> Preset:
    try:
        return mapping[name]
    except KeyError as exc:
        available = ", ".join(sorted(mapping)) or "none"
        raise ConfigurationError(f"Unknown {label} preset '{name}'. Allowed presets: {available}.") from exc
