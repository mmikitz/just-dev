# Open issues

Deferred findings from the Jira CLI exploratory QA report (see the
`claude/jira-cli-exploratory-execution-8q55i5` branch report, archived at
`docs/jira-cli-exploratory-report.pdf`). Both were
explicitly scoped out of the fix pass on `claude/project-review-fixes-mif32d`
because it is a recipe-syntax-level change, not a bug fix. Everything else
from that report (F1, F2, F3, F4, F6, R4, R5, U2, F5) has been fixed; see
that branch's commit and `attach-jira-issue`'s addition for details.

## U3 — No per-recipe `--help`

**Status: won't fix (resolved 2026-08-27).** `just <recipe> --help` is not
going to be made to work. Rationale below, kept alongside the original
analysis for context.

**Correction (2026-08-27, MCP tool-contract pass).** This resolution
originally named `just --list <namespace>` as the supported discovery path
for a recipe's *flags*. It is not one: `just --list jira` prints the literal
placeholder `[OPTIONS]` and no flag names at all. What does disclose them is
`just --show <recipe>` (raw attributes) and `just --dump --dump-format json`
(structured, and the basis for the manifest principle 22 asks for). Two
related facts, verified on `just 1.58.0`: `[arg(...)]` accepts `help=` and
`pattern=`, and this package currently sets neither, so every `help` field in
the dump is `null` and no enum is validated at the `just` layer. Adding both
needs no recipe-body change and does not reopen the shebang-branching cost
below. See `MCP-COMPATIBILITY-ANALYSIS.md`, F4.

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

**Alternative considered and adopted:** documenting the `just`-level
discovery paths instead of making `--help` work per recipe — they require no
code change and don't touch any recipe signature. See the resolution and its
correction at the top of this section for which paths actually disclose
flags.
