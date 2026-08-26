# Architecture

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
| `just update-jira-issue KEY [JSON]` | `just jira update-jira-issue KEY [JSON]` |
| `just delete-jira-issue KEY` | `just jira delete-jira-issue KEY` |
| `just create-pull-request TITLE` | `just bitbucket create-pull-request TITLE` |
| `just show-pull-request [ID]` | `just bitbucket show-pull-request [ID]` |
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
preview and require a TTY confirmation. The broker remains narrowly scoped:
Jira supports the four issue CRUD operations only, Jenkins accepts named
allowlisted presets and parameters, Bitbucket does not merge, and Confluence
writes only versioned preset pages.
