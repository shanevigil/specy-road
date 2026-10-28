#!/bin/sh
# claude-worker.sh <session> <prompt file>: start the session, or resume it.
# The create-or-resume wrapper from docs/orchestration-workers.md ("Roster setup"),
# verified on Claude Code 2.1.312; re-check after upgrading.
sid=$1 prompt=$2
PATH=/Users/savigil/WORKSPACE/specy-road/sr/tools:$PATH
export PATH
set -- -p --output-format stream-json --verbose --dangerously-skip-permissions --model claude-opus-5-5
if ls "$HOME"/.claude/projects/*/"$sid".jsonl >/dev/null 2>&1; then
  exec claude "$@" --resume "$sid" < "$prompt"
fi
exec claude "$@" --session-id "$sid" < "$prompt"
