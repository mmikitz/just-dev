from __future__ import annotations

import pytest

from just_dev.config import load_project_config, require_real_value
from just_dev.errors import ConfigurationError


def test_load_project_config_rejects_unknown_fields(tmp_path) -> None:
    config = tmp_path / "project.toml"
    config.write_text("[atlassian]\ncloud_id = 'x'\nunexpected = 'no'\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Invalid project configuration"):
        load_project_config(config)


@pytest.mark.parametrize("value", ["", "REPLACE_ME", "https://jenkins.example.invalid"])
def test_placeholders_are_not_accepted(value: str) -> None:
    with pytest.raises(ConfigurationError):
        require_real_value(value, "value")
