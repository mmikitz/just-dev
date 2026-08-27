# just-dev

This is the complete Getting Started guide for the portable `scripts/devtools/`
kit. It provides safe, repeatable Jira, Bitbucket, Jenkins, and Confluence
workflows through `just`.

## 1. Copy and import the kit

Copy the entire `scripts/devtools/` directory into the target repository, then
add this one line to the target repository's root `justfile`:

```just
import 'scripts/devtools/justfile'
```

Requirements are Python 3.12+, [uv](https://docs.astral.sh/uv/), and
`just >= 1.55`. Run `just check-devtools` after copying. Before using actions
that create a pull request or run CI, replace the starter verification command
in `scripts/devtools/recipes/project.just` with the target project's canonical
lint, test, and build command.

## 2. Configure `project.toml`

Copy `config/project.example.toml` to `config/project.toml` if needed, then
replace every placeholder. The file is safe to commit: it must not contain a
token, password, or KeePass master password.

For `[atlassian].cloud_id`, choose exactly one of these forms:

```toml
# An explicit Cloud ID is used unchanged.
[atlassian]
cloud_id = "00000000-0000-4000-8000-000000000123"
```

```toml
# A canonical site URL is resolved once through tenant metadata and cached
# locally in the selected auth profile.
[atlassian]
cloud_id = "https://example.atlassian.net"
```

Only a root `https://<site>.atlassian.net` URL is accepted. Do not supply an
`api.atlassian.com` gateway URL, a `/wiki` or REST path, a proxy URL, or an
HTTP URL. Jira and Confluence still use the scoped-token gateway internally.

## 3. Create KeePass entries and configure local auth

Create one KeePass entry per integration you intend to use. Put the scoped API
token in the entry's **Password** field, then copy the entry UUID. Suggested
entry titles are `just-dev/jira`, `just-dev/confluence`, `just-dev/bitbucket`,
and `just-dev/jenkins`; titles are for humans only—the UUID is what the tool
stores.

Create an initial profile with only the scopes available today:

```text
just configure-auth \
  --database ~/Secrets/developer.kdbx \
  --keyfile ~/Secrets/developer.key \
  --entry jira=KEEPASS_ENTRY_UUID \
  --entry bitbucket=KEEPASS_ENTRY_UUID
```

The user-local profile stores only the KeePass paths, entry UUIDs, and the
non-secret site-URL-to-Cloud-ID cache. It is not stored in the repository.

`configure-auth` is incremental: unchanged settings remain untouched. Add or
replace one scope later without re-entering every value:

```text
just configure-auth --entry confluence=KEEPASS_ENTRY_UUID
just configure-auth --database ~/Secrets/new-developer.kdbx
just configure-auth --clear-keyfile
just configure-auth --remove-entry jenkins
just configure-auth --profile work --entry jira=KEEPASS_ENTRY_UUID
```

`--entry` and `--remove-entry` may be repeated. `configure-auth` refreshes the
configured site's Cloud-ID cache. If tenant metadata is temporarily
unreachable, it warns and keeps an existing valid mapping.

## 4. Unlock, use, and recover credentials

Start the local broker when you need integrations:

```text
just unlock-secrets
just show-auth-status
```

The master-password prompt is local. Missing, empty, or unreadable token
entries generate safe warnings and do not stop the other available scopes from
unlocking. For example, a Jira token can be unavailable while Bitbucket still
works.

If an operation needs a scope that was not unlocked, it tells you the exact
repair path:

```text
just configure-auth --entry jira=KEEPASS_ENTRY_UUID
just unlock-secrets
```

If Jira or Confluence reports that the configured site has no Cloud ID, run
`just configure-auth` while connected to the site, or replace the site URL in
`project.toml` with the site's explicit UUID. Stop the broker when finished:

```text
just lock-secrets
```

`lock-secrets` waits for authenticated broker shutdown before discarding its
session metadata.

## Jira reads and output control

Use the Jira issue reader as follows:

```text
just read-jira-issue ISSUE \
  [--fields LIST] [--include links,attachments,comments] \
  [--view summary|full] [--format text|markdown|json] [--safe]
```

Jira defaults to a concise Markdown summary. `--fields` reduces the remote
payload, while `--include` opts into bulky nested sections. `--view full
--format json` is the complete machine-oriented representation. `--expand` and
`--properties` remain available for advanced Jira reads.

Examples:

```text
just read-jira-issue FUTUREAERO-20
just read-jira-issue FUTUREAERO-20 --fields summary,status,description --format text
just read-jira-issue FUTUREAERO-20 --include comments,links --view summary --format markdown
just read-jira-issue FUTUREAERO-20 --view full --format json --safe
```

Search for issues by JQL instead of a single key with `search-jira-issues`:

```text
just search-jira-issues JQL \
  [--fields LIST] [--view summary|full] [--limit N] \
  [--next-page-token TOKEN] [--expand LIST] [--format text|markdown|json] [--safe]
```

It shares the same field/view selection as `read-jira-issue`, but has no
`--include`: bulky per-issue sections (comments, attachments) don't belong in
a multi-issue list. `--limit` (1-100) maps to `maxResults`; use the returned
`nextPageToken` to fetch the next page.

```text
just search-jira-issues 'project = FUTUREAERO AND status = "In Progress"'
just search-jira-issues 'assignee = currentUser()' --fields summary,status --limit 20
just search-jira-issues 'project = FUTUREAERO' --view full --format json --safe
```

All public result recipes accept `--format text|markdown|json` and `--safe`.
Safe output structurally redacts identity/account fields, URLs, and
attachment metadata by replacing each value with `"[OMITTED]"` rather than
deleting the key — so a caller can tell "redacted by `--safe`" apart from
"absent in the source data", and any declared `outputSchema` (see
`describe-commands` below) still holds. It cannot reliably classify personal
information embedded in free text such as an issue description or comment.

## Machine-readable command discovery

```text
just describe-commands [--format text|markdown|json] [--safe]
```

Lists every command as an MCP-shaped tool descriptor — `name` (dotted by
namespace, e.g. `jira.read-jira-issue`), `description`, `inputSchema`,
`outputSchema` where the result shape is stable, and
`readOnly`/`destructive`/`idempotent` annotations — built from the CLI's own
Typer/Click introspection plus a small hand-written annotation table. Use
`--format json` for a script or an agent; `just --list <namespace>` remains
the right tool for a human skimming recipe names (it does not disclose flag
names — they print as the literal placeholder `[OPTIONS]`).

## Everyday commands

The flat form is preferred; the namespaced form is equivalent, for example
`just jira read-jira-issue ABC-123`.

```text
just check-devtools
just describe-commands --format json
just qa
just check-changed
just install-hooks
just configure-auth | unlock-secrets | show-auth-status | lock-secrets
just create-jira-issue bug "Summary" --description "Details" --extra-fields '{"customfield_10010":"Prod"}'
just read-jira-issue ABC-123 --fields summary,status
just search-jira-issues 'assignee = currentUser() AND status != Done' --limit 20
just update-jira-issue ABC-123 --summary "Updated summary" '{"notifyUsers":false}'
just update-jira-issue ABC-123 --labels "bug,urgent" --priority High
just update-jira-issue ABC-123 '{"update":{"issuelinks":[{"add":{"type":{"name":"Relates"},"outwardIssue":{"key":"ABC-124"}}}]}}'
just assign-jira-issue ABC-123 --assignee 5b10a2844c20165700ede21g
just assign-jira-issue ABC-123 --assignee jane.doe@example.com
just comment-jira-issue ABC-123 "Deployed to staging."
just attach-jira-issue ABC-123 ./screenshot.png
just transition-jira-issue ABC-123 "Done"
just delete-jira-issue ABC-123 --delete-subtasks
just create-pull-request "Title" --description "What changed and why" --reviewer alice --reviewer bob
just show-pull-request [ID]
just approve-pull-request 42
just decline-pull-request 42
just comment-pull-request 42 "Looks good, one nit inline."
just add-pull-request-reviewer 42 alice
just merge-pull-request 42 --merge-strategy squash --close-source-branch
just run-build PRESET
just show-build-status PRESET REF
just preview-release-notes FILE
just publish-release-notes FILE
just verify-project | run-ci
```

Mutating commands support `--dry-run` and `--yes`. Without `--yes`, the tool
shows a preview and requires interactive confirmation. A mutation's preview
is written to stderr, not stdout — `--format json`'s stdout always carries
exactly one JSON document, the result. Unlike every other mutation flag,
`--yes` has no environment counterpart: consent must be a real argument on
the command line, never an ambient setting one `export` could apply to every
mutation for a whole shell session. A recipe's own `--yes` flag is still
translated into a literal `--yes` argument before it reaches the CLI. A
lingering `JUST_DEV_YES=1` in the environment no longer waives anything; it
only prints `warning: JUST_DEV_YES no longer waives confirmation; pass
--yes` on stderr before the mutation fails closed the same way any
unconfirmed one does (exit `26`). Jira create presets control project, issue
type, labels, and components; custom `--extra-fields` cannot override those
preset-managed fields.

`assign-jira-issue --assignee` accepts either a Jira accountId or an email
address; an email is resolved to an accountId via Jira's user search, and the
command fails with a clear error if it matches zero or more than one user.

There is no dedicated flag for issue linking; use `update-jira-issue`'s raw
JSON body with Jira's own `issuelinks` update shape, as shown above.
`--summary`/`--description`/`--labels`/`--priority` and the JSON body's
`fields.*` cannot both set the same field in one call — the command rejects
the combination rather than silently picking one.

## CI and verification

CI does not start or modify a local broker or auth profile. In a CI process
(`CI=true`), inject only the needed credentials from the job's credential
store:

```text
JUST_DEV_CI_JIRA_TOKEN
JUST_DEV_CI_CONFLUENCE_TOKEN
JUST_DEV_CI_BITBUCKET_TOKEN
JUST_DEV_CI_JENKINS_TOKEN
```

A missing CI scope names the required variable in its error. Because CI
authenticates via those tokens rather than the local KeePass broker,
`show-auth-status` reports on the CI tokens instead (`source: ci`) when
`CI` is set, rather than the (always-absent) local broker session.

Run the main local checks from `scripts/devtools/` with:

```text
uv run --locked pytest
```

From the repository root, run the full local gate with:

```text
just qa
```

## Exit codes

Every command's exit code names the failure class, so scripts can branch on
it without parsing error text. Under `--format json`, a failure is also one
JSON document on stderr — `{"error": {"code": 25, "kind": "input_validation",
"message": "..."}}` — so a caller doesn't have to parse English to recover
the same detail; `kind` is a stable snake_case name derived from the error
class. Text and Markdown output keep the plain `error: ...` line unchanged.

| Code | `kind` (in `--format json` errors) | Meaning |
| ---- | ----------------------------------- | ------- |
| `0`  | —                       | Success. |
| `1`  | —                       | Unexpected/unhandled failure. |
| `2`  | —                       | CLI usage error (missing/unknown flag or argument). |
| `20` | `configuration`         | Configuration error (missing or invalid project/profile config). |
| `21` | `authentication`        | Authentication error (credentials rejected or missing). |
| `22` | `permission_denied`     | Permission denied by the remote service. |
| `23` | `conflict`              | Conflict (the remote resource changed since it was read). |
| `24` | `network`               | Network/remote-service error (including rate limiting). |
| `25` | `input_validation`      | Input validation error (bad argument, value, or remote 4xx rejection). |
| `26` | `confirmation`          | Confirmation refused (mutating command run without `--yes` outside a TTY). |
| `27` | `broker`                | Broker error (local credential broker failure). |
| `28` | `verification`          | Verification error (`verify-project`/`run-ci` check failed). |
