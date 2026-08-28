"""Build MCP-shaped tool descriptors for every CLI command via Typer introspection.

Each command becomes one descriptor: a dotted `namespace.command` name (matching
the collision prefix a `just <namespace> <command>` invocation already uses),
its help text as `description`, an `inputSchema` built from its Typer options
and arguments, an `outputSchema` where the result shape is genuinely stable,
and `annotations` (`readOnly`/`destructive`/`idempotent`) describing what the
command does to remote state. This does not make the CLI speak MCP's wire
protocol; it is the one machine-readable manifest an agent (MCP-shaped or not)
needs in order to discover the command surface without parsing `--help` text.
"""

from __future__ import annotations

from typing import Any

import typer.main
from typer.core import TyperArgument

_JSON_TYPES = {
    "str": "string",
    "text": "string",
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "boolean": "boolean",
    "path": "string",
    "uuid": "string",
}

# Spec defaults are readOnly=false, destructive=true, idempotent=false; every
# command below is annotated explicitly rather than relying on that default,
# since an unannotated tool tells an agent nothing and the default is the
# risky assumption. The nine Jira commands' values are the exact table derived
# in the MCP tool-contract compatibility analysis (does the command call
# `confirm_mutation`? does a retry duplicate, safely no-op, or fail without
# side effects?); every other command applies the same two questions.
ANNOTATIONS: dict[str, dict[str, bool]] = {
    "check-devtools": {"readOnly": True, "destructive": False, "idempotent": True},
    "describe-commands": {"readOnly": True, "destructive": False, "idempotent": True},
    "auth.configure-auth": {"readOnly": False, "destructive": False, "idempotent": True},
    "auth.unlock-secrets": {"readOnly": False, "destructive": False, "idempotent": True},
    "auth.show-auth-status": {"readOnly": True, "destructive": False, "idempotent": True},
    "auth.lock-secrets": {"readOnly": False, "destructive": False, "idempotent": True},
    "jira.create-jira-issue": {"readOnly": False, "destructive": False, "idempotent": False},
    "jira.read-jira-issue": {"readOnly": True, "destructive": False, "idempotent": True},
    "jira.search-jira-issues": {"readOnly": True, "destructive": False, "idempotent": True},
    "jira.update-jira-issue": {"readOnly": False, "destructive": True, "idempotent": True},
    "jira.assign-jira-issue": {"readOnly": False, "destructive": True, "idempotent": True},
    "jira.comment-jira-issue": {"readOnly": False, "destructive": False, "idempotent": False},
    "jira.attach-jira-issue": {"readOnly": False, "destructive": False, "idempotent": False},
    "jira.transition-jira-issue": {"readOnly": False, "destructive": True, "idempotent": True},
    # Not idempotent (R3): Jira returns 404 on delete whether the issue was already deleted or
    # never existed, so a retry after a dropped connection can't tell "already gone" from
    # "never existed" -- a blind retry risks silently no-oping on a re-used/typo'd key instead
    # of surfacing the real problem.
    "jira.delete-jira-issue": {"readOnly": False, "destructive": True, "idempotent": False},
    "bitbucket.create-pull-request": {"readOnly": False, "destructive": False, "idempotent": False},
    "bitbucket.show-pull-request": {"readOnly": True, "destructive": False, "idempotent": True},
    "bitbucket.approve-pull-request": {"readOnly": False, "destructive": False, "idempotent": False},
    "bitbucket.decline-pull-request": {"readOnly": False, "destructive": True, "idempotent": False},
    "bitbucket.comment-pull-request": {"readOnly": False, "destructive": False, "idempotent": False},
    "bitbucket.add-pull-request-reviewer": {"readOnly": False, "destructive": False, "idempotent": False},
    "bitbucket.merge-pull-request": {"readOnly": False, "destructive": True, "idempotent": False},
    "jenkins.run-build": {"readOnly": False, "destructive": False, "idempotent": False},
    "jenkins.show-build-status": {"readOnly": True, "destructive": False, "idempotent": True},
    "confluence.preview-release-notes": {"readOnly": True, "destructive": False, "idempotent": True},
    "confluence.publish-release-notes": {"readOnly": False, "destructive": True, "idempotent": False},
    "project.verify-project": {"readOnly": True, "destructive": False, "idempotent": True},
    "project.run-ci": {"readOnly": True, "destructive": False, "idempotent": True},
}

_DEFAULT_ANNOTATIONS = {"readOnly": False, "destructive": True, "idempotent": False}

# Per-parameter JSON Schema overrides for shapes a param's Click type alone
# can't express: a true enum (`--view`), a comma-separated finite vocabulary
# (`--include`), and the two object-valued flags (F8: `--extra-fields` on
# create and `request` on update are both a JSON object merged into the Jira
# request body; renaming create's former `--fields` off the name shared with
# read/search's comma-separated field list is what resolved the collision,
# not this override — this only declares the object shape Click's own type
# inference can't). Keyed by each param's manifest key (`_param_key`, R1),
# i.e. the same string that ends up in `inputSchema.properties` — not
# necessarily `param.name`, though every entry below happens to have both
# agree today.
SCHEMA_OVERRIDES: dict[str, dict[str, dict[str, Any]]] = {
    "jira.create-jira-issue": {
        "extra_fields": {
            "type": "object",
            "description": "Optional JSON object merged into 'fields', e.g. for custom fields.",
        },
    },
    "jira.update-jira-issue": {
        "request": {
            "type": "object",
            "description": (
                "Optional JSON object merged into the Edit issue request, e.g. custom fields or update operations."
            ),
        },
    },
    "jira.read-jira-issue": {
        "view": {"type": "string", "enum": ["summary", "full"], "description": "Issue view: summary or full."},
        "include": {
            "type": "array",
            "items": {"enum": ["links", "attachments", "comments"]},
            "description": "Optional sections; comma-separated on the command line.",
        },
    },
    "jira.search-jira-issues": {
        "view": {"type": "string", "enum": ["summary", "full"], "description": "Issue view: summary or full."},
    },
}

# outputSchema is declared only where the shape is stable regardless of what a
# specific issue happens to contain (F5): the default summary view and the
# search envelope. Jira's own `--view full` representation is intentionally
# left undeclared rather than pinned to whatever the API happens to return.
OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    "jira.read-jira-issue": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "key": {"type": "string"},
            "fields": {"type": "object"},
        },
        "required": ["fields"],
    },
    "jira.search-jira-issues": {
        "type": "object",
        "properties": {
            "issues": {"type": "array", "items": {"type": "object"}},
            "nextPageToken": {"type": "string"},
            "isLast": {"type": "boolean"},
            "total": {"type": "integer"},
        },
        "required": ["issues"],
    },
}


def _json_type(param: Any) -> str:
    type_name = getattr(param.type, "name", "") or ""
    return _JSON_TYPES.get(type_name, "string")


def _param_key(param: Any) -> str:
    """The manifest property key a consumer will kebab-case back into the flag they actually
    type (R1): for an option, that is its declared long flag (`--format` -> `format`, so it
    round-trips; `--dry-run` -> `dry_run` -> `--dry-run` is a no-op the same way), not
    `param.name` -- Typer sets that to the Python parameter name, and the two diverge whenever
    a command's parameter name doesn't match its own flag (every command's `output_format` is
    bound to `--format`, not `--output-format`). A positional argument has no flag at all, so
    it keeps `param.name`, which is also how `SCHEMA_OVERRIDES` below and the regression test
    in test_justfiles.py identify it.
    """

    if isinstance(param, TyperArgument):
        assert param.name is not None, "a positional argument exposed to the CLI always has a name"
        return param.name
    long_opts = [opt for opt in param.opts if opt.startswith("--")]
    flag = long_opts[0] if long_opts else param.opts[0]
    return flag.lstrip("-").replace("-", "_")


def _param_schema(dotted_name: str, key: str, param: Any) -> dict[str, Any]:
    override = SCHEMA_OVERRIDES.get(dotted_name, {}).get(key)
    if override is not None:
        schema = dict(override)
    elif getattr(param, "multiple", False):
        schema = {"type": "array", "items": {"type": _json_type(param)}}
    else:
        schema = {"type": _json_type(param)}
    if param.help and "description" not in schema:
        schema["description"] = param.help
    return schema


def _input_schema(dotted_name: str, command: Any) -> dict[str, Any]:
    # Keyed once per param and reused for `properties`, `required`, and the override lookup,
    # so the three can never reference three different names for the same parameter (R1).
    keyed_params = [(_param_key(param), param) for param in command.params]
    properties: dict[str, Any] = {}
    positional_index = 0
    for key, param in keyed_params:
        prop_schema = _param_schema(dotted_name, key, param)
        if isinstance(param, TyperArgument):
            # The CLI has no `--flag` for these at all (R1): a consumer that kebab-cases every
            # property name into a flag needs to know which ones instead take a bare value at
            # a fixed position, e.g. `just-dev jira read-jira-issue ABC-123`.
            prop_schema["x-cli-positional"] = True
            prop_schema["x-cli-positional-index"] = positional_index
            positional_index += 1
        properties[key] = prop_schema
    required = sorted(key for key, param in keyed_params if param.required)
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _descriptor(dotted_name: str, command: Any) -> dict[str, Any]:
    return {
        "name": dotted_name,
        "description": command.help or "",
        "inputSchema": _input_schema(dotted_name, command),
        **({"outputSchema": OUTPUT_SCHEMAS[dotted_name]} if dotted_name in OUTPUT_SCHEMAS else {}),
        "annotations": ANNOTATIONS.get(dotted_name, _DEFAULT_ANNOTATIONS),
    }


def _walk(group: Any, prefix: str, out: list[dict[str, Any]]) -> None:
    for name, sub in group.commands.items():
        if hasattr(sub, "commands"):
            _walk(sub, f"{prefix}{name}.", out)
        else:
            out.append(_descriptor(f"{prefix}{name}", sub))


def describe_commands(app: typer.main.Typer) -> list[dict[str, Any]]:
    """Build one MCP-shaped tool descriptor per command, sorted by name."""

    out: list[dict[str, Any]] = []
    _walk(typer.main.get_command(app), "", out)
    return sorted(out, key=lambda item: str(item["name"]))
