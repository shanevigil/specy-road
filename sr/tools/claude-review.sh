#!/bin/sh
# claude-review.sh <effort> <prompt text | prompt file>: one fallback reviewer turn on Claude Code (Opus), used
# sparingly when the Codex reviewer is unavailable. The prompt goes right after -p because
# --add-dir and --allowedTools take several values and would swallow it. Runs on the subscription
# login (--bare would need ANTHROPIC_API_KEY), so the launch mode is full. A prompt file (the roster's
# {prompt}) goes in on stdin instead: Linux caps one argument at 128 KiB.
effort=$1 prompt=$2
. "$(dirname "$0")/env.sh"
set -- --model claude-opus-5-5 --effort "$effort" --permission-mode acceptEdits \
  --allowedTools "Read,Grep,Glob,Write,Edit,Bash" --add-dir "$REVIEWS"
if [ -f "$prompt" ]; then exec claude -p "$@" < "$prompt"; fi
exec claude -p "$prompt" "$@" </dev/null
