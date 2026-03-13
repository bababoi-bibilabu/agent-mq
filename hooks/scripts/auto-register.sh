#!/usr/bin/env bash
# Auto-register this Claude Code session with agent-mq on startup.
# Runs as a SessionStart hook — silent on failure to avoid disrupting the session.

set -euo pipefail

MQ="${CLAUDE_PLUGIN_ROOT}/skills/mq/scripts/mq.py"

# Find the project dir for current working directory
PROJECT_HASH=$(pwd | tr '/' '-')
PROJECT_DIR="$HOME/.claude/projects/${PROJECT_HASH}"

if [ ! -d "$PROJECT_DIR" ]; then
    exit 0  # Not a known project, skip
fi

# Find the most recent transcript (= current session)
JSONL=$(ls -t "$PROJECT_DIR"/*.jsonl 2>/dev/null | head -1)
if [ -z "$JSONL" ]; then
    exit 0
fi

SESSION_ID=$(basename "$JSONL" .jsonl)
ALIAS=$(basename "$(pwd)")

python3 "$MQ" register "$SESSION_ID" --alias "$ALIAS" --desc "Session in $(pwd)" --tool claude-code 2>/dev/null || true
