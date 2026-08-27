# Open issues

Deferred findings from the Jira CLI exploratory QA report (see the
`claude/jira-cli-exploratory-execution-8q55i5` branch report). This one was
explicitly scoped out of the fix pass on `claude/project-review-fixes-mif32d`
because it is a recipe-syntax-level change, not a bug fix. Everything else
from that report (F1, F2, F3, F4, F6, R4, R5, U2, F5) has been fixed; see
that branch's commit and `attach-jira-issue`'s addition for details.

## U3 — No per-recipe `--help`

**Status:** deferred because it is the most invasive change in scope — it
touches the signature of every Jira recipe, not just adapter/workflow code.

**The problem:** `just read-jira-issue --help` fails with
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

**Alternative worth considering** before doing the full mechanical change:
a single `just <namespace>::<recipe> --help`-style shim recipe, or
documenting `just --list jira` / triggering a validation error on purpose
as the supported discovery paths (both already work per the QA report) and
closing this as "won't fix, use `--list`". That's a product call, not an
engineering one — flagging it here rather than deciding it unilaterally.
