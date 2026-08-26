# QA Strategy

## Quality objective and ownership

`main` remains releasable: no change merges with a failed required gate, a
coverage regression, or an unreviewed security-sensitive path. Developers own
reproducing and fixing failures before review; reviewers assess the behavioral
change, regression coverage, and risk rather than repeating CI output.

The team uses short-lived trunk-based branches targeting `main`. Pull requests
are squashed after the required checks, conversation resolution, and applicable
CODEOWNERS review. A repository administrator owns branch protections and may
remove any temporary owner bypass once a second reviewer is available.

## Test layers

- Unit tests cover configuration validation, Cloud-ID cache migration and
  refresh recovery, output rendering, safe filtering, confirmation policy, and
  token redaction.
- Broker lifecycle tests cover partial credential unlocks, authenticated IPC,
  stale state recovery, concurrent unlocks, expiry, and verified shutdown.
- Adapter contract tests use deterministic client mocks for scoped gateway URLs,
  request payloads, response normalization, and HTTP error translation.
- Workflow and CLI tests cover allowlists, missing-scope recovery guidance,
  Jira view/filter forwarding, and CI credential handling.
- Just recipe tests verify every flat alias and namespaced form, including
  spaces, special characters, repeated auth options, and output flags.
- `check-changed` tests verify staged-file-to-test selection and the full-suite
  fallback.

Live integration smoke tests are opt-in and use isolated Jira, Bitbucket,
Jenkins, and Confluence resources. Ordinary pull requests and forks receive no
integration credentials.

## Gates and CI

`just qa` is the local required-gate equivalent. It checks the lockfile,
formatting, Ruff linting, mypy, pytest, and branch coverage. CI additionally
builds the package and audits locked dependencies. The full pytest suite runs
on supported Python versions and native platform coverage includes Linux,
Windows, and WSL broker behavior.

The coverage floor is 67.51% and may rise after demonstrated improvement, not
fall. Flaky tests are not hidden by automatic retries: they require an owner,
ticket, and expiry; a temporary `xfail` must be explicit and justified.

Dependabot updates dependencies and GitHub Actions on the normal PR path. CI
uses minimal permissions, pinned actions, cancellation for superseded runs,
and no path filters that could skip a mandatory gate.

## Acceptance criteria

- `uv run --locked pytest` and `just qa` pass from a clean checkout.
- A copied `scripts/devtools/` directory works after the single root import and
  project verification customization.
- Both flat and namespaced recipe forms produce equivalent behavior.
- Cloud-ID UUID and site-URL configuration work without persisting a secret;
  CI leaves local profiles untouched.
- Partial local auth keeps independently configured integrations usable and
  gives a precise recovery command for a missing scope.
- Jira reads produce the documented summary/full, format, include, and safe
  behaviors without exposing credentials.
