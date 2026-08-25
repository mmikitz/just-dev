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

    try:
        return ProjectConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid project configuration: {exc}") from exc


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
