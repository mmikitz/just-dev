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

All public result recipes accept `--format text|markdown|json` and `--safe`.
Safe output structurally omits identity/account fields, URLs, and attachment
metadata. It cannot reliably classify personal information embedded in free
text such as an issue description or comment.

## Everyday commands

The flat form is preferred; the namespaced form is equivalent, for example
`just jira read-jira-issue ABC-123`.

```text
just check-devtools
just qa
just check-changed
just install-hooks
just configure-auth | unlock-secrets | show-auth-status | lock-secrets
just create-jira-issue bug "Summary" --description "Details" --fields '{"customfield_10010":"Prod"}'
just read-jira-issue ABC-123 --fields summary,status
just update-jira-issue ABC-123 --summary "Updated summary" '{"notifyUsers":false}'
just update-jira-issue ABC-123 --labels "bug,urgent" --priority High
just assign-jira-issue ABC-123 --assignee 5b10a2844c20165700ede21g
just comment-jira-issue ABC-123 "Deployed to staging."
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
shows a preview and requires interactive confirmation. Jira create presets
control project, issue type, labels, and components; custom `--fields` cannot
override those preset-managed fields.

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

A missing CI scope names the required variable in its error. Run the main local
checks from `scripts/devtools/` with:

```text
uv run --locked pytest
```

From the repository root, run the full local gate with:

```text
just qa
```
