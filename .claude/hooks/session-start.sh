#!/bin/bash
set -euo pipefail

# Only needed for Claude Code on the web sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Install `just` first so it's available even if the Jira config below fails.
command -v just >/dev/null 2>&1 || pip install rust-just

# CLOUD_ID and JIRA_PROJECT are injected per-session, not into the container
# build step, so this must run here (SessionStart) rather than in an
# environment "setup script".
: "${CLOUD_ID:?CLOUD_ID env var is required}"
: "${JIRA_PROJECT:?JIRA_PROJECT env var is required}"

config="${CLAUDE_PROJECT_DIR:-.}/scripts/devtools/config/project.toml"

sed -i.bak \
  -e "s|^cloud_id = .*|cloud_id = \"${CLOUD_ID}\"|" \
  -e "s|^project = .*|project = \"${JIRA_PROJECT}\"|" \
  "$config"
rm -f "${config}.bak"
