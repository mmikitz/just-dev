#!/bin/bash
set -uo pipefail

# Only needed for Claude Code on the web sessions.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# uv is already used throughout scripts/devtools and installs tools into an
# isolated environment, so it works even where `pip install` is blocked by
# PEP 668 (externally-managed-environment).
if ! command -v just >/dev/null 2>&1; then
  uv tool install rust-just || echo "session-start: failed to install just" >&2
fi

# CLOUD_ID and JIRA_PROJECT are injected per-session, not into the container
# build step, so this must run here (SessionStart) rather than in an
# environment "setup script". Never hard-fail session startup over Jira
# config: warn and leave the file untouched instead.
if [[ -z "${CLOUD_ID:-}" || -z "${JIRA_PROJECT:-}" ]]; then
  echo "session-start: CLOUD_ID and/or JIRA_PROJECT not set; leaving project.toml untouched." >&2
else
  config="${CLAUDE_PROJECT_DIR:-.}/scripts/devtools/config/project.toml"
  if [[ -f "$config" ]]; then
    sed -i.bak \
      -e "s|^cloud_id = .*|cloud_id = \"${CLOUD_ID}\"|" \
      -e "s|^project = .*|project = \"${JIRA_PROJECT}\"|" \
      "$config"
    rm -f "${config}.bak"
  else
    echo "session-start: ${config} not found; skipping Jira project config." >&2
  fi
fi

exit 0
