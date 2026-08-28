# Open issues

Deferred findings from the Jira CLI exploratory QA report (see the
`claude/jira-cli-exploratory-execution-8q55i5` branch report, archived at
`docs/jira-cli-exploratory-report.pdf`). Both were
explicitly scoped out of the fix pass on `claude/project-review-fixes-mif32d`
because it is a recipe-syntax-level change, not a bug fix. Everything else
from that report (F1, F2, F3, F4, F6, R4, R5, U2, F5) has been fixed; see
that branch's commit and `attach-jira-issue`'s addition for details.

## Fixed findings from the search/attach exploratory pass

`search-jira-issues` and `attach-jira-issue` shipped after the original
report and were never exercised by it. A follow-up exploratory session
(`claude/jira-commands-test-coverage-1jown7`) covered both live against
Jira Cloud and found three defects, all now fixed on this branch:

- **F7 — `search-jira-issues --view full` silently returned empty
  per-issue data when `--fields` wasn't also given.** `jira_fields_parameter()`
  omitted the `fields` query parameter for a full view with no explicit
  fields, which is the correct default for the single-issue read endpoint
  but not for `search/jql`, whose own default when `fields` is omitted is
  no fields at all. Fixed by sending an explicit `fields=*all` request
  instead of omitting the parameter when `view == "full"` and no fields
  were given.
- **F8 — `--safe` deleted `attach-jira-issue`'s entire result, not just
  PII.** `filter_safe_output()`'s redaction regex matched
  `attachment(?:s)?`/`filename` as a whole-key drop anywhere in the tree,
  but `attach-jira-issue`'s own result uses those exact names as top-level
  keys, so `--safe` reduced a successful attach's output to
  `{"issue_id_or_key": "..."}` — no confirmation anything was attached. The
  same collision silently emptied `read-jira-issue --include attachments
  --safe` too. Fixed by scoping the redaction to the genuinely sensitive
  nested/leaf fields (author, self, content URLs); structural metadata
  like `id`/`filename` now survives `--safe`.
- **U6 (medium) — `attach-jira-issue`'s default markdown/text output was a
  raw API dump, the same U2 gap the original report found for
  `read-jira-issue`.** With no `--format` given, a successful attach
  printed the full Jira attachment object — nested `author` with four
  avatar sizes, `self`/`content` URLs, `accountType`, `timeZone` — before
  the one line that answers "did it work" (`filename`, `size`). Fixed by
  giving `attach-jira-issue` a purpose-built one-line renderer
  (`render_attach_markdown`), the way `render_search_markdown` replaced
  the raw dump for search results.

## U3 — Per-recipe `--help`

**Status: fixed (resolved 2026-08-28).** Reverses the won't-fix below.
`just <recipe> --help` (e.g. `just read-jira-issue --help`) now works for
every recipe in `jira.just`, `bitbucket.just`, `jenkins.just`, and
`confluence.just` that has a required leading positional argument: it
reaches the Python CLI's own Typer-generated `--help` text instead of dying
in `just`'s recipe-level parser. `auth.just` needed no change — its
`*args` / `set positional-arguments` passthrough recipes already forwarded
`--help` straight through to the Python CLI before this fix.

**Why the two objections below turned out not to hold:**

- **Objection 1 (a required positional blocks `--help`) was correct, and is
  the fix.** Giving the leading positional a default of `''` (e.g.
  `read-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY=''` instead of a bare,
  required `$JUST_DEV_JIRA_ISSUE_ID_OR_KEY`) is what lets `just`'s parser
  hand `--help` off as an ordinary flag instead of rejecting it in the
  missing positional's place. Accepted, intentional consequence: `just
  read-jira-issue` (etc.) with no arguments now fails inside the Python
  CLI's own validation (`error: Issue ID or key is required.`, exit 25)
  instead of inside `just`'s parser (exit 2) — the same way every other
  missing required value already failed, and a fair trade for a working
  `--help`.
- **Objection 2 (would need a per-recipe branching shebang script) was
  wrong.** No shebang script was needed anywhere. The `--yes` mechanism
  already in every mutation recipe — `[arg('YES', long='yes', value='1',
  ...)]` plus `{{ if YES == '1' { '--yes' } else { '' } }}` conditional
  interpolation in the recipe body — is the exact mechanism reused for
  `--help`: `[arg('HELP', long='help', value='1', ...)]` plus a second
  `{{ if HELP == '1' { '--help' } else { '' } }}` conditional alongside it.
  Every recipe body is still a single `@uv run --locked just-dev ...` line.

`just --list <namespace>` and `just describe-commands` remain accurate and
useful exactly as the correction below describes — `--help` now covers
per-recipe flag discovery too, it doesn't replace either of them.

**Correction (2026-08-27, MCP tool-contract compatibility analysis):** the
original resolution overstated what `just --list <namespace>` actually
discloses. It prints only the literal placeholder `[OPTIONS]` for a
recipe's flags — no flag name is shown to a human or a machine:

```text
$ just --list jira
    read-jira-issue [OPTIONS] $JUST_DEV_JIRA_ISSUE_ID_OR_KEY
```

`--list` still covers recipe names and required positional arguments, but
it is not itself a flag-discovery path. `just describe-commands --format
json` remains the machine-readable manifest (see
`src/just_dev/introspect.py` and UX-DESIGN-PRINCIPLES.md principle 22);
`--help` (this section) now covers the human-readable one, and `--list`
remains the right tool for skimming recipe names.

**Original problem and won't-fix rationale (superseded 2026-08-28, kept for
context):** `just read-jira-issue --help` used to fail with `error: recipe
'read-jira-issue' does not have option '--help'` — `just`'s own argument
parser rejected the flag before the Python CLI (which already supported
`--help` via Typer) ever ran, across every recipe with a required leading
positional in `jira.just`, `bitbucket.just`, `jenkins.just`, and
`confluence.just`. The original won't-fix judged the mechanical fix —
making each leading positional optional, plus a per-recipe `--help` flag —
too invasive for the benefit, on the theory that it would require turning
every recipe body into a branching shebang script. It didn't: reusing the
existing `--yes` conditional-interpolation pattern (objection 2, above)
kept every recipe body a one-liner, which is what made the fix worth doing.

## Breaking changes from the MCP tool-contract review (F6, F8)

**Status: fixed.** The MCP-compatibility review (`Should just-dev speak
MCP?`, archived at `docs/jira-cli-exploratory-report.pdf` — its own
F-numbered findings are a separate series from the QA report's F-numbers
above) deliberately shipped only a mitigation for two findings because the
real fix breaks the CLI surface, then priced the breaking change as a
follow-up (`UX-DESIGN-PRINCIPLES.md` principles 22–23's "Do next" item).
Both are now fixed as breaking changes:

- **F8 — `--fields` meant two incompatible types across sibling
  commands.** `create-jira-issue --fields` took a JSON object;
  `read-jira-issue`/`search-jira-issues --fields` took a comma-separated
  field list — an agent generalizing from one call to the next could send
  a JSON object where Jira expects a CSV list and get a 4xx. Fixed by
  renaming `create-jira-issue`'s flag to `--extra-fields`
  (`JUST_DEV_JIRA_EXTRA_FIELDS` at the recipe layer). Migration:
  `just create-jira-issue ... --fields '{...}'` now fails at `just`'s own
  parser ("does not have option `--fields`"); replace with
  `--extra-fields`.
- **F6 — `JUST_DEV_YES=1` in the environment silently waived every
  mutation's confirmation.** One `export` — plausible in an agent harness,
  a CI shim, or a stray `.envrc` — removed the confirmation gate from all
  mutations for the rest of the session, with nothing in the logged
  command line to show it. Fixed by making consent argv-only: `--yes` has
  no environment counterpart anymore. Migration: a `JUST_DEV_YES=1` export
  now only prints a warning (`JUST_DEV_YES no longer waives confirmation;
  pass --yes`) and the mutation fails closed (exit `26`) exactly like any
  other unconfirmed one; pass `--yes` explicitly instead. Recipes still
  accept `--yes` at the `just` layer and translate it into a literal
  `--yes` argument.
