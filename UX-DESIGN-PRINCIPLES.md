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
mutation coverage; principle 12 was new to that pass. Principles 13–19 were
added after a later live-Jira exploratory QA pass (see
`docs/jira-cli-exploratory-report.pdf` and `OPEN_ISSUES.md`) whose findings
(F1–F3, F6, R5, U2) were fixed in code — the fix commit changed adapters,
workflows, and the CLI, but left this document unchanged, so the generalizable
lesson behind each fix wasn't captured anywhere a future change would see it
before repeating the same mistake with a new command. Principles 20–24 came
from a later pass that audited the CLI as an agent-facing surface against the
MCP tool contract (see `MCP-COMPATIBILITY-ANALYSIS.md`); unlike the others they
name gaps that are still open in the code, so they read as targets rather than
as descriptions of what already holds. Each principle below
cites something concrete and checkable in this codebase — a file, a test, or
an actual command's behavior — rather than an abstract claim.

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

## 13. Surface the remote service's own error detail (new in the QA-report pass)

Never let a failure collapse to a bare status code when the remote service
already sent back the reason. `_sdk_error` in `src/just_dev/adapters.py`
calls `_remote_error_detail` on any 4xx, which extracts Jira/Atlassian's own
`errorMessages`/`errors` body — redacted through the existing `redact_text`
filter — and appends it to the message instead of stopping at "Remote
service rejected the request (NNN)." Every adapter method decorated with
`@_sdk_errors(...)` gets this for free through the one shared mapper; a new
adapter method only loses it by raising its own exception instead of letting
`_sdk_errors` translate it. Before this fix, a nonexistent issue key, a
malformed key, and a 2000-character summary (Jira's real limit is 255) all
produced the identical three-word message.

## 14. Resolve a human-memorable identifier before rejecting it (new in the QA-report pass)

When an API demands an opaque ID but a human will always reach for the value
they actually have memorized, resolve it internally rather than erroring and
expecting the caller to already know the opaque shape. `JiraAdapter.
_resolve_assignee` in `adapters.py` passes a Jira accountId through
unchanged but resolves anything containing `@` via
`client.user_find_by_user_string`, and only raises `InputValidationError`
when that search is ambiguous or empty — it never silently guesses. Before
this fix, `assign-jira-issue --assignee someone@example.com` — the single
most obvious value to hand that flag — failed with an opaque 404, and the
only way to discover that an accountId was expected was to have already
read one out of a prior `read-jira-issue` response. A new command that
accepts a Jira/Bitbucket identity should ask the same question: is there a
human-obvious form of this ID, and can it be resolved instead of demanded?

## 15. Reject redundant or conflicting inputs; never pick a silent winner (new in the QA-report pass)

When a command can express the same intent through two different inputs in
one call — a raw JSON body and a named flag that touch the same field —
detect the overlap and fail with a clear `InputValidationError` naming the
conflicting names, rather than letting one silently win with no trace in
the preview, the dry-run output, or the real result.
`update_jira_issue`'s `conflicts = sorted(...)` check in `workflows.py`
(~line 316) runs before the request is ever built; `test_workflows.py`
covers both the rejected-overlap case and the allowed case where the JSON
body and flags touch disjoint fields. Before this fix, passing both a
positional JSON body and `--summary` with different values silently applied
the flag's value with no warning anywhere in the output. Apply the same
check to any future command that accumulates fields from more than one
input source.

## 16. A diagnostic command must check every credential path it claims to report on (new in the QA-report pass)

A status/diagnostic command exists to tell the truth about what's actually
happening; if it only inspects one of several ways the tool can be
authenticated, it will confidently lie under any other. `show_auth_status`
in `cli.py` used to always report on the local KeePass broker, even under
`CI=true`, where the broker never starts and the CI env-var tokens are what
every other command actually authenticates with — so the one command a new
user or CI maintainer is told to run first gave a false negative while
every real operation succeeded. It now branches on `_ci_enabled()` and
reports `BrokerStatus(source="ci")` off the configured CI scopes instead.
When a capability has more than one way of establishing state, the command
whose whole job is reporting that state must check all of them, not just
the one built first.

## 17. Validate what's cheap and local before spending a network round-trip (new in the QA-report pass)

A syntactically-impossible input should fail immediately and specifically,
not be sent to the remote API only to come back as the same generic 4xx as
a real "not found." `DevtoolsService._jira_issue_id_or_key` in
`workflows.py` rejects a value that doesn't match a plausible Jira key or
numeric ID before any broker call;
`test_workflows.py::test_jira_commands_reject_a_malformed_issue_key_before_calling_the_broker`
asserts zero broker calls for a malformed key. This complements principle
13, not replaces it — the remote call can still fail for reasons only the
server can know (an issue that doesn't exist, a field that's too long); this
principle only front-loads the subset of validation that never needed to
ask the server at all.

## 18. A stable, documented exit-code contract (new in the QA-report pass)

Every distinct failure class — usage error, config error, auth error,
permission denied, conflict, network, input validation, confirmation
refused, broker error, verification error — maps to one fixed exit code
(see the error classes in `src/just_dev/errors.py`), documented in the
"Exit codes" table in `scripts/devtools/README.md`. A script or CI job
should be able to branch on the code alone without parsing message text.
Before this was documented, the split already existed in code but nothing
in `--list` or any error named it, so a CI author would have had to
reverse-engineer it by triggering every error class once — exactly as the
QA session did. When a change introduces a genuinely new failure class,
give it its own code and add a row; don't fold it into an existing code
whose meaning would then stop being precise. (Whether this table should
also be surfaced somewhere `--help`-visible, per principle 2, rather than
living only in `README.md`, is still open — flag it if you touch this
area.)

## 19. Default output leads with the answer, not the whole response body (new in the QA-report pass)

The default read output for a resource must foreground the handful of
fields a person actually asked for — status, assignee, summary — as a
compact line or two, not walk the full nested API payload (avatar sizes,
`self` URLs, `accountType`, timezone) before reaching them. Before this
fix, `read-jira-issue`'s markdown, text, and JSON output all rendered the
identical raw dump — same field count, same noise, just different
punctuation, with no lean option. `render_issue_markdown` in `jira.py` now
renders status/assignee/reporter/priority as a single compact line per
field; `test_jira_reads.py::test_render_issue_markdown_keeps_identity_fields_compact`
pins this. `--view full`/`--format json` remain how an agent gets the
complete representation (principle 6); the default should not require
scrolling to answer the obvious question.

## 20. One invocation, one machine-readable result (new in the MCP tool-contract pass)

Under `--format json`, everything a command writes to stdout must parse as
exactly one JSON document. Previews, warnings, and progress commentary are not
results: they belong on stderr, and `--dry-run` is what returns a preview *as*
the result. Known violation to fix rather than copy: a confirmed mutation
currently emits the preview and the result as two documents on stdout, because
`workflows.py` calls `announce(preview)` even when `--yes` was passed and
`cli.py` binds `announce` to a stdout emit (`MCP-COMPATIBILITY-ANALYSIS.md`,
F1/F2).

## 21. A failure is machine-readable too (new in the MCP tool-contract pass)

Principle 18's exit code says *which* class failed; under `--format json` the
message must say *what* failed in the same structured form a success gets —
`{"error": {"code", "kind", "message"}}` on stderr, not prose. Principle 13's
remote error detail is the payload that matters here, and it is unreachable to a
caller that has to parse English for it. Text and Markdown keep today's line;
exit codes never change meaning.

## 22. Declare the machine contract; don't only document it (new in the MCP tool-contract pass)

Anything an automated caller needs — a parameter's type, an enum's members,
whether a command is read-only, destructive, or safe to retry — must be
obtainable *from a command*, not only from a `help=` sentence. This is principle
2 applied to the audience that cannot read prose. Two corollaries with current
counterexamples: one flag name means one type across sibling commands
(`--fields` is a JSON object on `create-jira-issue` and a comma-separated list
on the two reads), and a mutation that duplicates on retry says so before it is
called (`create-jira-issue`, `comment-jira-issue`, and `attach-jira-issue` have
no idempotency key and nothing that admits it).

## 23. Consent is an argument, not an ambient setting (new in the MCP tool-contract pass)

Principle 9's fail-closed confirmation is only as strong as its narrowest
bypass. `JUST_DEV_*` variables exist so recipes can carry *data* into the CLI
without shell interpolation (principle 7); a waived confirmation is not data.
`_flag_or_environment` currently accepts `JUST_DEV_YES=1` from an inherited
environment, so one `export` silently un-gates every later mutation with no
trace in the command line anyone reviews. A waiver that did not come from the
command line must at minimum announce itself on stderr.

## 24. Cross-call state is an explicit argument (new in the MCP tool-contract pass)

Anything a caller must carry from one invocation to the next is a value the
command hands back and accepts again — never state the tool remembers on the
caller's behalf. `search-jira-issues` is the worked example: it returns
`nextPageToken` and takes `--next-page-token`, so a paged read is reproducible
from its arguments alone. The credential broker is the deliberate counterpart,
not a counterexample: its session is unlocked by a human and never travels as
an argument, which is exactly why the auth lifecycle is not scriptable and
`show-auth-status` exists to report which state applies.

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
10. **Re-check against principles 1–24** — does `--help` alone explain it?
    Does it accept `--format`/`--safe`? Does it preview and confirm before
    writing? Would an agent scripting against it need to know anything this
    document and `--help` don't already say? Does every remote-calling method
    raise through `_sdk_errors(...)` so a 4xx surfaces the server's own error
    detail (13)? If it takes an identity value, is there a human-obvious form
    of it, and is that resolved rather than demanded (14)? If it can accept
    the same field from two input sources, does it reject the overlap instead
    of picking a silent winner (15)? If it reports on state, does it check
    every path that state can come from, not just the interactive one (16)?
    Does it reject cheaply-checkable-locally input before any network call
    (17)? Does a genuinely new failure class get its own exit code, added to
    the README table (18)? Does its default output lead with the fields a
    person actually asked for (19)? Does one `--format json` invocation write
    exactly one JSON document to stdout, with any preview on stderr (20)? Does a
    failure carry its detail structurally, not only as prose (21)? Are its types,
    enums, and read-only/destructive/retry-safe behavior obtainable from a
    command rather than only from `help=` text, and does every flag name it
    reuses keep the type its siblings give it (22)? Does an
    environment-supplied confirmation waiver announce itself (23)? Does any
    state it needs across calls travel as an explicit argument (24)?
