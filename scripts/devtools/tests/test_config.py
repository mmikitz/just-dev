from __future__ import annotations

import pytest

from just_dev.atlassian import normalize_site_url
from just_dev.config import load_project_config, require_real_value
from just_dev.errors import ConfigurationError
from just_dev.models import AtlassianSettings


def test_load_project_config_rejects_unknown_fields(tmp_path) -> None:
    config = tmp_path / "project.toml"
    config.write_text("[atlassian]\ncloud_id = 'x'\nunexpected = 'no'\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="Invalid project configuration"):
        load_project_config(config)


@pytest.mark.parametrize("value", ["", "REPLACE_ME", "https://jenkins.example.invalid"])
def test_placeholders_are_not_accepted(value: str) -> None:
    with pytest.raises(ConfigurationError):
        require_real_value(value, "value")


def test_atlassian_cloud_id_accepts_a_uuid_or_normalizes_a_canonical_site_url() -> None:
    assert AtlassianSettings(cloud_id="00000000-0000-4000-8000-000000000123").cloud_id.endswith("0123")
    assert AtlassianSettings(cloud_id="https://EXAMPLE.atlassian.net/").cloud_id == "https://example.atlassian.net"
    assert normalize_site_url("https://example.atlassian.net") == "https://example.atlassian.net"


@pytest.mark.parametrize(
    "value",
    [
        "http://example.atlassian.net",
        "https://example.atlassian.net/wiki",
        "https://api.atlassian.com/ex/jira/id",
        "https://example.atlassian.net?proxy=yes",
        "example.atlassian.net",
    ],
)
def test_atlassian_cloud_id_rejects_noncanonical_site_urls(value: str) -> None:
    with pytest.raises(ValueError, match="UUID or canonical"):
        AtlassianSettings(cloud_id=value)
