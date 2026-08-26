# UX design principles for `scripts/devtools/`

This CLI is a shared surface: humans run it interactively, AI agents drive it
as a scripted tool, and CI invokes it as a program. All three consume the same
commands, the same `--help`, and the same output contract. A change that reads
well for a human at a terminal but leaves an agent guessing — or vice versa —
is a regression even if every test passes. The principles below exist so that
future changes to the CLI and its `just` targets keep serving all three
audiences at once, not just the one the author had in mind.

Most of these were established by a review pass that audited the CLI for
discoverability and learnability gaps before this pass added Jira/Bitbucket
mutation coverage; the last principle is new to this pass. Each principle
below cites something concrete and checkable in this codebase — a file, a
test, or an actual command's behavior — rather than an abstract claim.

## The principles

**1. Self-describing `--help`.** A command's `--help` output must be enough
on its own to use it correctly — no README lookup required. Every option in
`src/just_dev/cli.py` carries a `help=` string for exactly this reason (see
any `typer.Option(...)` call, e.g. `update-jira-issue`'s `--labels`/
`--priority`).

**2. Nothing README-only.** Any usage detail that actually matters must be
discoverable from the CLI itself. Prose docs (`README.md`, this file) explain
and give examples; they do not carry information the tool doesn't already
expose, because prose drifts out of sync with the code and the CLI can't.

**3. Errors teach the fix.** An error should name the next command to run,
not just report failure. Two concrete instances already in this codebase:
`require_preset` in `src/just_dev/config.py` — `"Unknown {label} preset
'{name}'. Allowed presets: {available}."` — and `_token` in
`src/just_dev/operations.py`, whose `AuthenticationError` names the exact
repair path: `` "No {scope} token is available in the unlocked profile. Add it
with `just configure-auth --entry {scope}=KEEPASS_ENTRY_UUID` and then run
`just unlock-secrets`." `` This pass's `transition-jira-issue` follows the same
convention: an unrecognized status raises `"Unknown status '{status}'. Allowed
transitions: {available}."`, listing the transitions Jira actually returned —
not a static list that can drift from the real workflow.

**4. One output contract.** Every command supports the same `--format
text|markdown|json` and `--safe` flags, applied uniformly through
`_set_command_output_options` and `_emit` in `cli.py`. No command invents its
own output flavor or a bespoke flag for a variant of the same idea.

**5. Structured-data-first.** Prefer typed, structured fields over prose blobs
so an agent or script can consume output without parsing English — see the
`PullRequestResult`/`IssueResult`/`BuildResult` models in `models.py`, returned
as JSON when `--format json` is set rather than a formatted sentence.

**6. Filter-at-source.** Let the caller narrow what's fetched instead of
fetching everything and filtering client-side. `read-jira-issue`'s
`--fields`/`--include`/`--view` reduce the actual Jira response server-side
(see `jira_fields_parameter` in `src/just_dev/jira.py`), rather than the CLI
downloading the full issue and trimming it locally.

**7. Shell-safe flags.** User-supplied values must never enter a shell string
substitution. Recipes pass every value through `just`'s `$`-exported
parameters — see the comment at the top of `recipes/jira.just`: "`$`-prefixed
parameters are exported by just. User input never enters a shell
substitution." `tests/test_justfiles.py::
test_special_characters_and_spaces_survive_without_shell_interpolation` is the
concrete regression test for this: it round-trips a Jira summary containing
`&`, `$()`, `"`, `;`, and `rm -rf /` and asserts it arrives byte-for-byte
unchanged.

**8. Flat + namespaced parity.** Every command works identically as a
top-level alias (`just update-jira-issue`) and in its namespaced form (`just
jira update-jira-issue`) — never two slightly different behaviors wearing one
name. `tests/test_justfiles.py::test_each_public_alias_has_its_namespaced_target`
and `::test_alias_and_namespace_form_run_the_same_recipe` enforce this for
every alias, including the 8 this pass adds.

**9. Previewable, safe mutations.** Every mutating command supports
`--dry-run` to preview the exact request without writing, and refuses to
proceed without `--yes` outside an interactive TTY — it fails closed rather
than silently blocking on a prompt nobody can answer. This is
`confirm_mutation` in `src/just_dev/confirmation.py`, used by every mutation
in `workflows.py` without exception, including all 8 added in this pass.

**10. Discovery over tribal knowledge.** A user shouldn't need out-of-band
knowledge the tool could have told them — Jira preset names, allowed Jenkins
build parameters, and (as of this pass) the exact set of destination statuses
a given issue can transition to. Where this still has real gaps — for
example, there is still no `just`-level way to discover Jira workflow status
names for an issue *before* attempting a transition, short of trying one and
reading the resulting error's "Allowed transitions" list — note them honestly
as follow-ups rather than claiming full coverage.

**11. Watch `just --list` doc-comment placement.** The one-line summary
`just --list` shows for a recipe comes from the *last* comment line
immediately preceding it, with no blank line in between — and it silently
drops everything before that last line. This is verifiable today:
`recipes/quality.just`'s `check-changed` recipe has a two-line explanatory
comment above it —

```just
# Fast pre-commit gate: lints, type-checks, and tests only staged changes.
# Called by the Lefthook pre-commit hook installed via `install-hooks`.
check-changed:
```

— but `just --list quality` shows only the second line:

```text
check-changed            # Called by the Lefthook pre-commit hook installed via `install-hooks`.
```

The first line isn't wrong, but it's invisible from `--list` — a reader only
sees it by opening the file. A misplaced or multi-line doc-comment produces a
missing or misleading `just --list` summary without any error, which is
exactly the kind of silent discoverability gap the original review pass
flagged. When adding a recipe, put the single most useful sentence on the
line directly above it, not the first line of a longer explanation.

## 12. One target, one backend action (new in this pass)

A `just` target must map to one coherent backend action. It must never
conditionally branch between semantically different REST calls depending on
which flags happen to be set — that turns a single command's behavior into an
untestable combinatorial surface and hides "this flag actually talks to a
different endpoint" from both `--help` and the reader.

A composite read-then-write call is still fine when the API genuinely
requires resolving state before writing — `publish-release-notes` reads the
current Confluence page version before its versioned write, and this pass's
`transition-jira-issue` reads the issue's available transitions before
resolving which one to fire — because that's one coherent action taking two
calls, not two different actions living under one name.

This pass is the worked example. Before it, `update-jira-issue` only had
dedicated `--summary`/`--description` fields; comments and transitions live on
separate Jira REST sub-resources (`/issue/{key}/comment`,
`/issue/{key}/transitions`) that `update-jira-issue`'s `PUT /issue/{key}`
never touches. Concretely, there was no way to comment on or transition a
Jira issue through this CLI at all — not even through `update-jira-issue`'s
JSON-passthrough escape hatch, because that escape hatch only reaches the
generic issue-edit endpoint. Bolting `--comment`/`--transition` flags onto
`update-jira-issue` would have "solved" that by making one command silently
call one of three different endpoints depending on which flag was set. Instead
`assign-jira-issue`, `comment-jira-issue`, and `transition-jira-issue` became
three new commands. The same reasoning produced five new Bitbucket commands
(`approve-pull-request`, `merge-pull-request`, `decline-pull-request`,
`comment-pull-request`, `add-pull-request-reviewer`) instead of flags bolted
onto `create-pull-request` — `operations.py`'s allowlist had no path to any of
those five endpoints at all before this pass.

Conversely, this principle is *not* "always prefer a new command." `--labels`
and `--priority` correctly became `update-jira-issue` flags, because Jira's
priority and labels fields live in the exact same `PUT /issue/{key}` body as
summary and description — one endpoint, more fields. Likewise
`--description`, `--reviewer`, and `--close-source-branch` correctly became
`create-pull-request` flags: they're fields in the same create-PR POST body,
not a different endpoint. The test is not "is this a new field?" — it's "does
satisfying this request mean calling a different endpoint?" If yes, new
command. If no, new flag.

## Checklist for adding a new command

1. **Decide: new command or new flag?** Apply principle 12 above. If the
   capability requires a different REST endpoint than an existing command
   already calls, it's a new command. If it's another field in the same
   request body, it's a flag on the existing command.
2. **`recipes/{service}.just`** — add (or extend) a recipe block:
   `[working-directory(devtools_root)]` + `[env('JUST_DEV_PROJECT_ROOT',
   project_root)]` + one `[arg('JUST_DEV_X', long='x')]` per flag (including
   `--dry-run`/`--yes`/`--format`/`--safe` for a mutation), then a
   positional-env-var recipe signature that just calls `uv run --locked
   just-dev <module> <command>`.
3. **`justfile`** — add `alias <command> := <module>::<command>` so the flat
   and namespaced forms both exist (principle 8).
4. **`src/just_dev/cli.py`** — a `@{service}_app.command(...)` function:
   `context: typer.Context` first, every value routed through
   `_argument_or_environment` / `_optional_value_or_environment` /
   `_flag_or_environment` / `_option_or_environment` (never typer's native
   "required parameter" mechanism — recipes pass values via env vars with
   CLI defaults of `None`), always ending `dry_run, yes, profile,
   output_format, safe` for a mutation. Call `_set_command_output_options`
   then `_execute(context, lambda: ...)`.
5. **`src/just_dev/workflows.py`** (`DevtoolsService`) — validate inputs,
   build a `PreviewResult`, return it immediately if `dry_run` (before any
   broker call — principle 9), else `announce(preview)` then
   `confirm_mutation("<action phrase>", yes=yes)`, then
   `self.broker.invoke("<operation>", self._payload(...))`.
6. **`src/just_dev/operations.py`** — one new `elif operation == "..."` branch
   in `execute_operation`. This function is a hard allowlist; there is no way
   to reach an adapter method except through a branch here.
7. **`src/just_dev/adapters.py`** — a thin method on the relevant adapter that
   makes the actual call. Prefer a real SDK method when one exists and its
   Cloud behavior is verified (declare it narrowly on the client's
   `Protocol`); fall back to a raw `resource_url`/`get`/`post`/`put`/`delete`
   call, exactly like `JiraAdapter` already does throughout and like this
   pass's `approve_pull_request` does, when the wrapped SDK method doesn't
   match Bitbucket Cloud's actual documented endpoint shape.
8. **Tests** — extend the fakes in `tests/test_operations.py`,
   `tests/test_workflows.py`, and `tests/test_adapters.py`; add the command to
   `ALIASES`/`RECIPES` in `tests/test_justfiles.py`; add a `--dry-run` case to
   `tests/test_cli.py` if it's a new command (not just a new flag).
9. **Docs** — one example line in `README.md`'s everyday-commands block, one
   row in `ARCHITECTURE.md`'s command table.
10. **Re-check against principles 1–11** — does `--help` alone explain it?
    Does it accept `--format`/`--safe`? Does it preview and confirm before
    writing? Would an agent scripting against it need to know anything this
    document and `--help` don't already say?
