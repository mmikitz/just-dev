from __future__ import annotations

from just_dev.cli import app
from just_dev.introspect import describe_commands


def _tool(name: str) -> dict:
    tools = {tool["name"]: tool for tool in describe_commands(app)}
    return tools[name]


def test_every_tool_name_is_dotted_by_namespace_or_top_level() -> None:
    names = [tool["name"] for tool in describe_commands(app)]

    assert names == sorted(names)
    assert "jira.read-jira-issue" in names
    assert "check-devtools" in names
    assert "describe-commands" in names


def test_jira_annotations_match_the_compatibility_analysis_table() -> None:
    assert _tool("jira.read-jira-issue")["annotations"] == {
        "readOnly": True,
        "destructive": False,
        "idempotent": True,
    }
    assert _tool("jira.create-jira-issue")["annotations"] == {
        "readOnly": False,
        "destructive": False,
        "idempotent": False,
    }
    assert _tool("jira.delete-jira-issue")["annotations"] == {
        "readOnly": False,
        "destructive": True,
        "idempotent": False,
    }


def test_fields_type_collision_is_resolved_by_rename_not_just_declared() -> None:
    """F8: create-jira-issue's object-valued flag is named --extra-fields, distinct
    from read/search's comma-separated --fields, so no flag name carries two types."""

    create_properties = _tool("jira.create-jira-issue")["inputSchema"]["properties"]
    assert create_properties["extra_fields"]["type"] == "object"
    assert "fields" not in create_properties
    assert _tool("jira.update-jira-issue")["inputSchema"]["properties"]["request"]["type"] == "object"
    assert _tool("jira.read-jira-issue")["inputSchema"]["properties"]["fields"]["type"] == "string"
    assert _tool("jira.search-jira-issues")["inputSchema"]["properties"]["fields"]["type"] == "string"


def test_view_is_declared_as_a_true_enum() -> None:
    view_schema = _tool("jira.read-jira-issue")["inputSchema"]["properties"]["view"]

    assert view_schema["enum"] == ["summary", "full"]


def test_output_schema_is_declared_only_for_stable_views() -> None:
    assert "outputSchema" in _tool("jira.read-jira-issue")
    assert "outputSchema" in _tool("jira.search-jira-issues")
    assert "outputSchema" not in _tool("jira.update-jira-issue")


def test_multi_value_options_become_array_schemas() -> None:
    entry_schema = _tool("auth.configure-auth")["inputSchema"]["properties"]["entry"]

    assert entry_schema["type"] == "array"


def test_every_command_has_a_non_empty_description() -> None:
    """R1: 15 commands -- everything but the nine Jira commands and the two top-level
    commands -- had no docstring and so no description in the manifest, silently telling
    an agent nothing about what they do. Enumerated via describe_commands(app) rather than
    hand-listed (this test used to only check the nine Jira names), so a newly added command
    with no docstring fails here instead of quietly joining the gap."""

    for tool in describe_commands(app):
        assert tool["description"], f"{tool['name']} should have a non-empty description"
