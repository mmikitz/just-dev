# Architecture

## Goals

The overarching goal of this project is to make software delivery teams —
PdM, PM, dev, and test — more productive in their daily workflows. Everything
else in this document is in service of that, and it is why the CLI must be:

- **Learnable.** A new user shouldn't need to read documentation, let alone
  the source code, to get something done. They need to be able to learn how
  to accomplish their goals from `--help` output and from error/success
  messages alone. See `UX-DESIGN-PRINCIPLES.md` principles 1–3 and 10.
- **Easy to use.** Goals should be quick and easy to accomplish with minimal
  interaction, especially recurring ones — sensible defaults, few required
  flags, no unnecessary ceremony.
- **Functionally correct.** Commands do exactly what they claim, with no
  silent partial failures — e.g. a command must reject two inputs that
  conflict rather than silently letting one win. See
  `UX-DESIGN-PRINCIPLES.md` principle 15.
- **Robust**, including helpful error messages. Failure modes are handled
  explicitly and reported in a way that names the next step, not a stack
  trace or a generic exception, and a remote rejection surfaces the remote
  service's own reason rather than a bare status code. See
  `UX-DESIGN-PRINCIPLES.md` principles 3, 13, and 17.

## Boundaries and layout

`scripts/devtools/` is a portable, self-contained integration package. A host
project adds only this root import:

```just
import 'scripts/devtools/justfile'
```

The package owns its Python CLI, Just modules, configuration schema, adapters,
and tests. `project.just` is the deliberately small project-specific boundary:
it supplies the host project's canonical verification command. The root
`lefthook.yml` is necessarily outside the package because Lefthook discovers it
only from the repository root.

The flat verb-object aliases are the canonical public surface. Namespaced forms
invoke the same recipe and remain supported.

| Flat command | Namespaced command |
| --- | --- |
| `just configure-auth` | `just auth configure-auth` |
| `just unlock-secrets` | `just auth unlock-secrets` |
| `just show-auth-status` | `just auth show-auth-status` |
| `just lock-secrets` | `just auth lock-secrets` |
| `just create-jira-issue PRESET SUMMARY` | `just jira create-jira-issue PRESET SUMMARY` |
| `just read-jira-issue KEY` | `just jira read-jira-issue KEY` |
| `just search-jira-issues JQL` | `just jira search-jira-issues JQL` |
| `just update-jira-issue KEY [JSON]` | `just jira update-jira-issue KEY [JSON]` |
| `just assign-jira-issue KEY --assignee ACCOUNT_ID` | `just jira assign-jira-issue KEY --assignee ACCOUNT_ID` |
| `just comment-jira-issue KEY COMMENT` | `just jira comment-jira-issue KEY COMMENT` |
| `just attach-jira-issue KEY FILE_PATH` | `just jira attach-jira-issue KEY FILE_PATH` |
| `just transition-jira-issue KEY STATUS` | `just jira transition-jira-issue KEY STATUS` |
| `just delete-jira-issue KEY` | `just jira delete-jira-issue KEY` |
| `just jira-integration-smoke` | `just jira jira-integration-smoke` |
| `just create-pull-request TITLE` | `just bitbucket create-pull-request TITLE` |
| `just show-pull-request [ID]` | `just bitbucket show-pull-request [ID]` |
| `just approve-pull-request PR_ID` | `just bitbucket approve-pull-request PR_ID` |
| `just decline-pull-request PR_ID` | `just bitbucket decline-pull-request PR_ID` |
| `just comment-pull-request PR_ID COMMENT` | `just bitbucket comment-pull-request PR_ID COMMENT` |
| `just add-pull-request-reviewer PR_ID REVIEWER` | `just bitbucket add-pull-request-reviewer PR_ID REVIEWER` |
| `just merge-pull-request PR_ID` | `just bitbucket merge-pull-request PR_ID` |
| `just run-build PRESET` | `just jenkins run-build PRESET` |
| `just show-build-status PRESET REF` | `just jenkins show-build-status PRESET REF` |
| `just preview-release-notes FILE` | `just confluence preview-release-notes FILE` |
| `just publish-release-notes FILE` | `just confluence publish-release-notes FILE` |

## Configuration model

`config/project.toml` is checked in and contains no credentials. Its
`[atlassian].cloud_id` is either an explicit UUID or a canonical
`https://<site>.atlassian.net` URL. Arbitrary REST, proxy, and product URLs are
rejected. Explicit UUIDs are used unchanged.

When the value is a site URL, the CLI reads the site's tenant metadata and
obtains its Cloud ID. A local auth profile stores the resulting non-secret
mapping as `cloud_ids = { "https://site.atlassian.net" = "UUID" }`. Cache
keys are normalized site URLs. Profile updates use an atomic, owner-only JSON
write; raw tokens never enter that file.

`configure-auth` explicitly refreshes the current project's mapping. A site
URL not already cached is also resolved during unlock or before a Jira or
Confluence operation. A refresh failure keeps a previously valid mapping. An
operation with no usable mapping fails with instructions to refresh local auth
or configure an explicit UUID. CI resolves a configured site URL in the job
only and never reads or writes a local profile.

Jira and Confluence always call their scoped-token gateway:

```text
https://api.atlassian.com/ex/{product}/{cloudId}/...
```

Bitbucket retains its separate Cloud API token and Jenkins its configured
credential. This gateway design follows Atlassian's [scoped-token
guidance](https://support.atlassian.com/confluence/kb/scoped-api-tokens-in-confluence-cloud/).

## Secret and broker lifecycle

A local profile contains a KeePass database path, optional keyfile, scoped
entry UUIDs, and the non-secret Cloud-ID cache. It is intentionally outside
the repository. Profiles may name any subset of `jira`, `confluence`,
`bitbucket`, and `jenkins`.

Unlock reads the available KeePass passwords into memory and sends them over an
anonymous pipe to a detached local broker. Missing, empty, or inaccessible
scope entries cause safe stderr warnings; the broker starts with the remaining
tokens. The broker uses HMAC-authenticated JSON IPC (`AF_UNIX` on Linux/WSL,
`AF_PIPE` on Windows), returns no raw token, and permits only the allowlisted
operations implemented by the service.

The broker expires after at most eight hours. `lock-secrets` first confirms an
authenticated shutdown, then removes session metadata; if shutdown cannot be
confirmed, metadata is retained rather than risking a live session being
forgotten. Separate Windows, WSL, and Linux environments have separate
sessions.

Every broker-backed operation checks its own scope. A local missing scope names
the exact `configure-auth --entry SCOPE=KEEPASS_ENTRY_UUID` and
`unlock-secrets` recovery path. In CI it instead names the required
`JUST_DEV_CI_<SCOPE>_TOKEN` credential.

## Interface policy

All public result recipes accept `--format text|markdown|json` and `--safe`.
Text is compact plain output, Markdown is readable structured output, and JSON
is machine-oriented. The Jira read command defaults to a concise Markdown
summary. Use `--view full --format json` when an automation needs the complete
issue representation.

```text
just read-jira-issue ISSUE \
  [--fields LIST] [--include links,attachments,comments] \
  [--view summary|full] [--format text|markdown|json] [--safe]
```

`--fields` reduces the Jira response server-side. `--include` opts into bulky
links, attachment, and comment sections. `--expand` and `--properties` remain
advanced Jira read parameters. `--safe` structurally omits identity/account
fields, URLs, and attachment metadata. It cannot perfectly classify PII in
arbitrary free text such as descriptions or comments.

Mutating commands retain `--dry-run` and `--yes`; without `--yes`, they show a
preview and require a TTY confirmation. `--yes` is argv-only — unlike every
other mutation flag it has no environment counterpart, so consent can never
travel as an ambient setting. The broker remains narrowly scoped to a
hard allowlist in `execute_operation`, never an open passthrough: Jira
supports create, read, update, and delete plus assign, comment, and
transition; Bitbucket supports create and show plus approve, merge, decline,
comment, and add-reviewer; Jenkins accepts named allowlisted presets and
parameters; and Confluence writes only versioned preset pages. See
`UX-DESIGN-PRINCIPLES.md` for the principle governing when a capability
becomes a new command versus a new flag on an existing one.
