"""Fast pre-commit gate: lints, type-checks, and tests only staged changes.

Invoked by `just check-changed` (see quality.just), which the Lefthook
pre-commit hook (../../lefthook.yml) calls on every `git commit`. `just qa`
remains the full, authoritative gate; this is a narrower, faster local check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DEVTOOLS_ROOT = Path(__file__).resolve().parents[1]
SRC = DEVTOOLS_ROOT / "src" / "just_dev"
TESTS = DEVTOOLS_ROOT / "tests"


def staged_files() -> list[Path]:
    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=DEVTOOLS_ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    )
    diff = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=DEVTOOLS_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [repo_root / entry for entry in diff.stdout.split("\0") if entry]


def select_tests(
    changed_src: list[Path], changed_tests: list[Path], changed_just: list[Path]
) -> tuple[set[Path], bool]:
    """Map changed files to the test files that cover them.

    Returns (test files to run, whether to fall back to the full suite instead).
    A source file with no test file matching its stem falls back to the full
    suite, since that means either the mapping is too naive (e.g. a module
    shared across many tests) or the module genuinely has no dedicated test.
    """
    if any(path.name == "conftest.py" for path in changed_tests):
        return set(), True

    targets = set(changed_tests)
    for src_file in changed_src:
        matches = [path for path in TESTS.glob("test_*.py") if src_file.stem in path.stem]
        if not matches:
            return set(), True
        targets.update(matches)

    if changed_just:
        justfile_tests = TESTS / "test_justfiles.py"
        if justfile_tests.exists():
            targets.add(justfile_tests)

    return targets, False


def run(*args: str) -> bool:
    print("+", " ".join(args))
    return subprocess.run(args, cwd=DEVTOOLS_ROOT).returncode == 0


def main() -> int:
    files = staged_files()
    changed_src = sorted(p for p in files if p.suffix == ".py" and p.is_relative_to(SRC))
    changed_tests = sorted(p for p in files if p.suffix == ".py" and p.is_relative_to(TESTS))
    changed_just = [p for p in files if p.suffix == ".just" or p.name == "justfile"]

    if not changed_src and not changed_tests and not changed_just:
        print("check-changed: no staged files under scripts/devtools/, nothing to do")
        return 0

    ok = True

    lint_targets = [str(p.relative_to(DEVTOOLS_ROOT)) for p in (*changed_src, *changed_tests)]
    if lint_targets:
        ok &= run("uv", "run", "--locked", "ruff", "format", "--check", *lint_targets)
        ok &= run("uv", "run", "--locked", "ruff", "check", *lint_targets)
    if changed_src:
        ok &= run("uv", "run", "--locked", "mypy", *(str(p.relative_to(DEVTOOLS_ROOT)) for p in changed_src))

    test_targets, full_suite = select_tests(changed_src, changed_tests, changed_just)
    if full_suite:
        print("check-changed: change has no narrow test mapping, running the full suite")
        ok &= run("uv", "run", "--locked", "pytest")
    elif test_targets:
        rel_targets = sorted(str(p.relative_to(DEVTOOLS_ROOT)) for p in test_targets)
        print(f"check-changed: running {len(rel_targets)} test file(s): {', '.join(rel_targets)}")
        ok &= run("uv", "run", "--locked", "pytest", *rel_targets)

    if not ok:
        print("check-changed: failed - `just qa` runs the full gate, `git commit --no-verify` skips this hook")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
