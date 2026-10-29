#!/bin/sh
# claude-review.sh <effort> <prompt text>: one fallback reviewer turn on Claude Code (Opus), used
# sparingly when the Codex reviewer is unavailable. The prompt goes right after -p because
# --add-dir and --allowedTools take several values and would swallow it.
effort=$1 prompt=$2
PATH=/Users/savigil/WORKSPACE/specy-road/sr/tools:$PATH
export PATH
exec claude -p "$prompt" --model claude-opus-5-5 --effort "$effort" --permission-mode acceptEdits \
  --allowedTools "Read,Grep,Glob,Write,Edit,Bash" \
  --add-dir /Users/savigil/WORKSPACE/specy-road/sr/work/reviews </dev/null
