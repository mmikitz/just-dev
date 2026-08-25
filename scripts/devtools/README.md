# just-dev

`scripts/devtools/` is a self-contained starter kit for safe, repeatable Jira,
Bitbucket, Jenkins and Confluence workflows. Copy the whole directory into a
target project and add exactly this line to its root `justfile`:

```just
import 'scripts/devtools/justfile'
```

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- `just >= 1.55` (modules and submodule aliases are required)

The host project must tailor `config/project.toml` and replace the
`project_verify_command` in `recipes/project.just` with its canonical lint,
test, and build command. `just check-devtools` deliberately fails until the
`JUST_DEV_REPLACE_ME` starter hook has been replaced.

Secrets never belong in `project.toml`, a `.env` file, command arguments, or
environment variables. Configure a local KeePass profile instead:

```text
just configure-auth
just unlock-secrets
just show-auth-status
```

The profile (KeePass path, optional keyfile, and entry UUIDs only) is stored in
the user configuration directory. Unlock starts a per-platform local broker;
the broker receives tokens through an anonymous pipe and expires after at most
eight hours. `just lock-secrets` stops it early.

## Commands

The flat command is preferred; the equivalent namespaced form remains
available, for example `just create-jira-issue bug "Summary"` and
`just jira create-jira-issue bug "Summary"`.

```text
just check-devtools
just configure-auth | unlock-secrets | show-auth-status | lock-secrets
just create-jira-issue bug "Summary" --description "Details" --fields '{"customfield_10010":"Prod"}'
just read-jira-isdue ABC-123 --fields summary,status --expand names
just update-jira-issue ABC-123 --summary "Updated summary" '{"notifyUsers":false}'
just delete-jira-issue ABC-123 --delete-subtasks
just create-pull-request "Title"
just show-pull-request [ID]
just run-build PRESET
just show-build-status PRESET REF
just preview-release-notes FILE
just publish-release-notes FILE
just verify-project | run-ci
```

Recipes forward safe, exported parameters, including mutation flags:

```text
just create-jira-issue bug "Summary" --dry-run
just update-jira-issue ABC-123 '{"update":{"labels":[{"add":"triaged"}]}}' --yes
just create-pull-request "Title" --yes
just run-build test --parameter REF=main --dry-run
```

The direct CLI exposes the same options for scripting or CI.

### Jira request parameters

The Jira module exposes exactly these four targets:

```text
create-jira-issue PRESET SUMMARY [--description TEXT] [--fields JSON]
read-jira-isdue ISSUE_ID_OR_KEY [--fields LIST] [--expand LIST] [--properties LIST]
update-jira-issue ISSUE_ID_OR_KEY [--summary TEXT] [--description TEXT] [REQUEST_JSON]
delete-jira-issue ISSUE_ID_OR_KEY [--delete-subtasks]
```

`PRESET` names a `[jira.presets.<name>]` entry in `project.toml` (`project`,
`issue_type`, `labels`, `components`) — the mechanism that resolves and
enforces it lives in the portable tool code (`workflows.py` for an early
check, `operations.py` in the privileged broker for the authoritative one);
only the preset's *values* are project-specific, in `project.toml`. The broker
always rebuilds `project`/`issuetype`/`labels`/`components` from the preset
itself, so `--fields` cannot override them — attempting to set one of those
keys is rejected before the broker is even called.

- `create-jira-issue` sends the preset's fields plus `summary`, an optional
  `--description` (wrapped as Atlassian Document Format), and an optional
  `--fields` JSON object merged in for custom fields.
- `read-jira-isdue` exposes the Get-issue query parameters `fields`, `expand`,
  and `properties` as comma-separated flags.
- `update-jira-issue` keeps a full JSON request body (`fields`, `update`,
  `notifyUsers`, and the rest of the Edit-issue payload) as its escape hatch —
  update supports array add/remove operations that don't map onto flags —
  plus `--summary`/`--description` shortcuts merged into `fields`.
- `delete-jira-issue` exposes `deleteSubtasks` as a boolean flag.

Every mutating operation supports `--dry-run` and `--yes`. Without `--yes`, a
TTY confirmation is required. `create-pull-request --no-verify` is guarded by
the same explicit confirmation and never changes an existing open PR.

## Configuration and permissions

Named Jenkins presets are an allowlist. Arbitrary jobs, deploy jobs,
administrative actions, merges, and bulk actions are intentionally absent. Jira
is restricted at the broker to the four issue CRUD operations above, and
`create-jira-issue` additionally only ever files into the project/issue type
named by its preset. Jira and Confluence use separate scoped tokens through
the Atlassian gateway; Bitbucket uses its own token. CI obtains credentials
only through the Jenkins credentials store and does not use the local broker.
In a CI process (`CI=true`), inject scoped credentials from that store as
`JUST_DEV_CI_JIRA_TOKEN`, `JUST_DEV_CI_CONFLUENCE_TOKEN`,
`JUST_DEV_CI_BITBUCKET_TOKEN`, and/or `JUST_DEV_CI_JENKINS_TOKEN`; these names
are ignored outside CI.

Run the test suite with:

```text
uv run --locked pytest
```
