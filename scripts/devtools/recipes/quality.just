import 'common.just'

# The local equivalent of the mandatory GitHub pull-request gates.
[working-directory(devtools_root)]
qa:
    @uv lock --check
    @uv run --locked ruff format --check .
    @uv run --locked ruff check .
    @uv run --locked mypy src
    @uv run --locked pytest --cov=just_dev --cov-branch --cov-report=term-missing

# Fast pre-commit gate: lints, type-checks, and tests only staged changes.
# Called by the Lefthook pre-commit hook installed via `install-hooks`.
[working-directory(devtools_root)]
check-changed:
    @uv run --locked python recipes/check_changed.py

# Installs the Lefthook-managed Git hooks defined in the repository's lefthook.yml.
[working-directory(devtools_root)]
install-hooks:
    @uv run --locked lefthook install
