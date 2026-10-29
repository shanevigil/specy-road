#!/bin/sh
# claude-review.sh <effort> <prompt text>: one fallback reviewer turn on Claude Code (Opus), used
# sparingly when the Codex reviewer is unavailable. The main checkout's sr/work/reviews is added
# so the reviewer can write its REVIEW and notes files there.
effort=$1 prompt=$2
PATH=/Users/savigil/WORKSPACE/specy-road/sr/tools:$PATH
export PATH
exec claude -p --model claude-opus-5-5 --effort "$effort" --permission-mode acceptEdits \
  --add-dir /Users/savigil/WORKSPACE/specy-road/sr/work/reviews \
  --allowedTools "Read,Grep,Glob,Write,Edit,Bash" "$prompt" </dev/null
