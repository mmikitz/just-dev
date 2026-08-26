- Cloud ID or URL

- Getting Started (what to copy, what to change, how to enter tokens into keepass
    - PLAN.md vs QA-KONZEPT.md vs scripts/devtools/README.md

- conigure-auth:

    - should be possible to skip to enter tokens for tools not yet used (and later on added)
        - broker redacting output should work with empty tokens
    - is pretty annoying in case a single thing needs to be changed (need to go through every piece of config again)

- unlock-screcets:

    - should still work even if not all tokens are available (with warning logged)

- any tool recipe:

    - if tokens not available, should fail with helpful error message (e.g., to add tokens to keepass database)

- "read-jira-isdue"

    - rename to "read-jira-issue"

    - add output formats: markdown for humans and AI; json for programms

    - output filters:

        >   I’d use explicit flags rather than a vague --filter:
        >
        >   - --fields summary,status,assignee,reporter,description — server-side payload reduction.
        >   - --include links,attachments,comments — opt into bulky nested sections.
        >   - --view summary|full — concise human/AI view versus complete issue data.
        >   - --format text|json|markdown — presentation only.
        >   - --safe — omit personal data, account IDs, URLs, and attachment metadata.
        >
        >   For example:
        >
        >   just read-jira-isdue FUTUREAERO-20 \
        >     --fields summary,status,assignee,reporter,description \
        >     --view summary \
        >     --format markdown
        >
        >   Keep a full + json mode for automation, but make the concise view the practical default for people and AI.

    - apply the above two to other commands where reasonable

- just lock-secrets

    - close broker

- not helpful error message:

  > ❯ just read-jira-isdue FUTUREAERO-20
  > error: Jira request failed.
  > error: recipe `read-jira-isdue` failed on line 19 with exit code 24
