#!/bin/sh
# fable-worker.sh <session> <prompt file>: start or resume a Claude Fable 5.1 executor session.
# Same create-or-resume wrapper as claude-worker.sh (docs/orchestration-workers.md, "Roster setup"),
# with the model pinned to claude-fable-5-1. Verified on Claude Code 2.1.312; re-check after upgrading.
sid=$1 prompt=$2
PATH=$HOME/.local/bin:/opt/homebrew/bin:$PATH   # where the claude CLI may live outside the login PATH
. "$(dirname "$0")/env.sh"
set -- -p --output-format stream-json --verbose --dangerously-skip-permissions --model claude-fable-5-1
if ls "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/projects/*/"$sid".jsonl >/dev/null 2>&1; then
  exec claude "$@" --resume "$sid" < "$prompt"
fi
exec claude "$@" --session-id "$sid" < "$prompt"
