"""Live Jira integration smoke test for the `jira` recipes.

Opt-in only (see QA-STRATEGY.md's "Live integration smoke tests are opt-in" test layer): this drives
the real `just jira::*` recipes over the network against whatever Jira site the ambient environment
points at (the checked-in default config, or a personal account layered in via TEST_CLOUD_ID /
TEST_JIRA_PROJECT -- see config.py's overlay). It is never run by `just qa` or `run-ci` and needs no
mocking, since its entire point is to catch what mocks can't: real Jira REST responses, real workflow
transitions, and the actual recipe -> just-dev -> Atlassian round trip.

Invoke with `just jira-integration-smoke`. Requires unlocked credentials for the active profile (see
`just show-auth-status` / `just unlock-secrets`) and a `bug` preset in the resolved project config.

Creates two throwaway issues, exercises create -> assign -> transition -> comment -> link -> delete
end to end, and always deletes what it created, even on failure -- if a delete itself fails the
leftover keys are printed so they can be cleaned up by hand.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SUMMARY_PREFIX = "just-dev integration smoke"
_KEY_PATTERN = re.compile(r'"key":\s*"([A-Z][A-Z0-9]*-\d+)"')


class SmokeFailure(RuntimeError):
    """Raised for a step whose outcome doesn't match what the recipe should have done."""


def run_just(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["just", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def run_just_json(*args: str) -> Any:
    """Run a recipe with --format json and return its result object.

    A mutating recipe invoked with --yes still prints a preview line before the result line (confirmed
    during the exploratory session: `just create-jira-issue ... --yes` echoes `{"preview": ...}` then
    `{"id": ..., "key": ...}`), so --format json output is JSON Lines, not a single JSON document -- the
    result is always the last non-blank line.
    """
    completed = run_just(*args, "--format", "json")
    if completed.returncode != 0:
        raise SmokeFailure(f"`just {' '.join(args)}` failed (exit {completed.returncode}):\n{completed.stderr}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise SmokeFailure(f"`just {' '.join(args)}` produced no output:\n{completed.stdout!r}")
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"`just {' '.join(args)}` did not return JSON:\n{completed.stdout}") from exc


def step(label: str) -> None:
    print(f"-- {label}")


def create_issue(summary_suffix: str, created: list[str]) -> str:
    """Create an issue and register its key in `created` for cleanup -- including when the call itself
    raises, since a JSON-parsing bug here once left a real issue created but untracked (caught during
    validation of this script): the key is salvaged straight out of the raw output in that case too."""
    try:
        result = run_just_json("create-jira-issue", "bug", f"{SUMMARY_PREFIX}: {summary_suffix}", "--yes")
    except SmokeFailure as exc:
        salvaged = _KEY_PATTERN.search(str(exc))
        if salvaged:
            created.append(salvaged.group(1))
        raise
    key = result.get("key")
    if not key:
        raise SmokeFailure(f"create-jira-issue did not return a key: {result}")
    created.append(str(key))
    return str(key)


def discover_a_transition_other_than(key: str, current_status: str) -> str:
    """No transition name is safe to hardcode -- workflows are per-project config, not CLI behavior.
    Deliberately request a bogus status: the CLI's own error names every valid transition (this is the
    "Unknown status 'X'. Allowed transitions: A, B, C." message the exploratory session found and the
    unit suite pins in test_workflows.py), so we parse it instead of assuming what the site calls things."""
    probe = run_just("transition-jira-issue", key, "__smoke_test_invalid_status__")
    marker = "Allowed transitions: "
    if marker not in probe.stderr:
        raise SmokeFailure(f"could not discover valid transitions from:\n{probe.stderr}")
    allowed = [name.strip() for name in probe.stderr.split(marker, 1)[1].split(".")[0].split(",")]
    for name in allowed:
        if name and name != current_status:
            return name
    raise SmokeFailure(f"no transition other than '{current_status}' is available among {allowed}")


def delete_issue(key: str) -> None:
    result = run_just_json("delete-jira-issue", key, "--yes")
    if not result.get("deleted"):
        raise SmokeFailure(f"delete-jira-issue did not confirm deletion: {result}")


def main() -> int:
    created: list[str] = []
    failures: list[str] = []

    try:
        step("dry-run create makes no real issue")
        preview = run_just("create-jira-issue", "bug", f"{SUMMARY_PREFIX}: dry-run", "--dry-run")
        if preview.returncode != 0 or "key" in preview.stdout:
            raise SmokeFailure(f"--dry-run appears to have created something:\n{preview.stdout}")

        step("create issue A")
        issue_a = create_issue("lifecycle issue A", created)

        step("read issue A back")
        read_back = run_just_json("read-jira-issue", issue_a)
        if read_back["fields"]["summary"] != f"{SUMMARY_PREFIX}: lifecycle issue A":
            raise SmokeFailure(f"read-back summary mismatch: {read_back['fields']['summary']!r}")
        reporter_account_id = read_back["fields"]["reporter"]["accountId"]
        current_status = read_back["fields"]["status"]["name"]

        step("assign issue A to the reporter's own account (a portable, always-valid accountId)")
        assign_result = run_just_json("assign-jira-issue", issue_a, "--assignee", reporter_account_id, "--yes")
        if assign_result.get("assignee") != reporter_account_id:
            raise SmokeFailure(f"assign-jira-issue did not echo the assignee: {assign_result}")

        step("transition issue A to a discovered, non-hardcoded status")
        next_status = discover_a_transition_other_than(issue_a, current_status)
        transition_result = run_just_json("transition-jira-issue", issue_a, next_status, "--yes")
        if not transition_result.get("transitioned"):
            raise SmokeFailure(f"transition-jira-issue did not confirm: {transition_result}")

        step("comment on issue A")
        comment_result = run_just_json("comment-jira-issue", issue_a, "Posted by the integration smoke test.", "--yes")
        if "id" not in comment_result:
            raise SmokeFailure(f"comment-jira-issue did not return a comment id: {comment_result}")

        step("create issue B as a link target")
        issue_b = create_issue("link target issue B", created)

        step("link A -> B via the raw-JSON escape hatch (no dedicated linking flag exists)")
        link_request = json.dumps(
            {"update": {"issuelinks": [{"add": {"type": {"name": "Relates"}, "outwardIssue": {"key": issue_b}}}]}}
        )
        link_result = run_just_json("update-jira-issue", issue_a, link_request, "--yes")
        if not link_result.get("updated"):
            raise SmokeFailure(f"update-jira-issue did not confirm the link update: {link_result}")

        step("read issue A with --include links,attachments,comments and check the link landed")
        full_read = run_just_json("read-jira-issue", issue_a, "--include", "links,attachments,comments")
        links = full_read["fields"].get("issuelinks", [])
        linked_keys = {entry.get("outwardIssue", {}).get("key") for entry in links}
        if issue_b not in linked_keys:
            raise SmokeFailure(f"issue B ({issue_b}) is not among issue A's links: {links}")
        if full_read["fields"].get("attachment") != []:
            raise SmokeFailure(
                f"expected an empty attachment list on a fresh issue: {full_read['fields'].get('attachment')}"
            )

    except SmokeFailure as exc:
        failures.append(str(exc))

    for key in created:
        try:
            delete_issue(key)
        except SmokeFailure as exc:
            failures.append(f"cleanup failed for {key}: {exc}")

    if failures:
        print("\nFAIL:")
        for failure in failures:
            print(f"  - {failure}")
        leftover = [
            key for key in created if any(key in failure for failure in failures if "cleanup failed" in failure)
        ]
        if leftover:
            print(f"\nLeftover issues that may need manual cleanup: {', '.join(leftover)}")
        return 1

    print(f"\nPASS: created, linked, and cleaned up {', '.join(created)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
