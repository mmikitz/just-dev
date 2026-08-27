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
        "idempotent": True,
    }


def test_fields_type_collision_is_resolved_per_command_not_globally() -> None:
    """F8: --fields is a JSON object on create/update, a CSV field list on read/search."""

    assert _tool("jira.create-jira-issue")["inputSchema"]["properties"]["fields"]["type"] == "object"
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


def test_jira_commands_have_a_non_empty_description() -> None:
    for name in (
        "jira.create-jira-issue",
        "jira.read-jira-issue",
        "jira.search-jira-issues",
        "jira.update-jira-issue",
        "jira.assign-jira-issue",
        "jira.comment-jira-issue",
        "jira.attach-jira-issue",
        "jira.transition-jira-issue",
        "jira.delete-jira-issue",
    ):
        assert _tool(name)["description"], f"{name} should have a non-empty description"
