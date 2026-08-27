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

## U3 — No per-recipe `--help`

**Status: won't fix (resolved 2026-08-27).** `just --list <namespace>` (e.g.
`just --list jira`) is the supported discovery path for a recipe's flags;
`just <recipe> --help` is not going to be made to work. Rationale below,
kept alongside the original analysis for context.

**Correction (2026-08-27, MCP tool-contract compatibility analysis):** the
resolution above overstates what `just --list <namespace>` actually
discloses. It prints only the literal placeholder `[OPTIONS]` for a
recipe's flags — no flag name is shown to a human or a machine:

```text
$ just --list jira
    read-jira-issue [OPTIONS] $JUST_DEV_JIRA_ISSUE_ID_OR_KEY
```

`--list` still covers what it was originally credited for (recipe names and
required positional arguments), so the won't-fix stands for `just <recipe>
--help` specifically. But it is not itself a flag-discovery path, and
nothing else machine-readable filled that gap until `just describe-commands`
was added: a manifest of every command's flags, types, and behavior hints
built from the Python CLI's own Typer/Click introspection (see
`src/just_dev/introspect.py` and UX-DESIGN-PRINCIPLES.md principle 22). Use
`just describe-commands --format json` for machine discovery; `just --list
<namespace>` remains the right tool for a human skimming recipe names.

**Why won't-fix:** every recipe body in `scripts/devtools/recipes/*.just` is
today a trivial one-liner that delegates entirely to the Python CLI — none
of the ~25 recipes across `jira.just`, `bitbucket.just`, `jenkins.just`, and
`confluence.just` contain any shell logic. The mechanical fix below would
introduce the first branching shebang script into that layer, repeated
across every recipe, and would also require making each recipe's leading
positional argument optional so `just <recipe> --help` doesn't also demand
its normal required input — pushing a validation responsibility from
`just`'s own parser onto the Python CLI, with its own test coverage per
recipe. That's a real style break for a benefit `just --list <namespace>`
already provides today with zero code changes. `UX-DESIGN-PRINCIPLES.md`'s
principles don't require per-recipe `--help` specifically — principle 1
("self-describing `--help`") is satisfied by the Typer CLI's own `--help`,
which already works once a command is actually invoked; the gap is purely
`just`'s recipe-level flag parsing, and `--list` covers that discovery need
without touching recipe signatures at all.

**Original problem description (for context):**

`just read-jira-issue --help` fails with
`error: recipe 'read-jira-issue' does not have option '--help'` — `just`'s
own argument parser rejects the flag before the Python CLI (which *does*
support `--help` via Typer) ever runs. This affects all 7 recipes in
`scripts/devtools/recipes/jira.just`, and likely the other integrations'
recipes too (`bitbucket.just`, `jenkins.just`, `confluence.just`) for the
same structural reason.

**Why it's invasive:** every recipe today invokes the CLI with zero
arguments — all values flow in through `[arg(...)]`-declared environment
variables (see `scripts/devtools/recipes/jira.just`), and the Python side
reads them back out via `_argument_or_environment`/`_optional_value_or_environment`
in `cli.py`. Making `--help` work means:

1. Adding a `[arg('JUST_DEV_HELP', long='help', value='1')]` flag to every
   recipe signature.
2. Making every recipe's leading positional argument (e.g.
   `$JUST_DEV_JIRA_ISSUE_ID_OR_KEY`, currently mandatory with no default)
   optional, since `just read-jira-issue --help` must not also demand an
   issue key.
3. Changing each recipe body from the current one-liner
   (`@uv run --locked just-dev jira read-jira-issue`) to a shebang script
   that branches on the help flag, e.g.:

   ```just
   read-jira-issue $JUST_DEV_JIRA_ISSUE_ID_OR_KEY='' ... $JUST_DEV_HELP='':
       #!/usr/bin/env bash
       if [ -n "$JUST_DEV_HELP" ]; then
           exec uv run --locked just-dev jira read-jira-issue --help
       else
           exec uv run --locked just-dev jira read-jira-issue
       fi
   ```

   (Typer's own `--help` output works fine once actually invoked — the gap
   is purely `just`'s recipe-level argument parsing getting in the way
   first.)
4. Repeating this for all 7 Jira recipes, then the equivalent recipes in
   the other integration modules if the fix should be consistent
   CLI-wide (recommended, since the same `--help` convention should hold
   for every `just <recipe>` the same way).
5. New/updated tests in `test_justfiles.py` (the existing alias/namespace
   parity + shell-safety test file) asserting `just <recipe> --help`
   exits 0 and prints the recipe's Typer help text, for at least one
   recipe per integration.

**Alternative considered and adopted:** documenting `just --list jira` (and
the other namespaces) as the supported discovery path instead — it already
works per the QA report, requires no code change, and doesn't touch any
recipe signature. See the resolution at the top of this section.

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
