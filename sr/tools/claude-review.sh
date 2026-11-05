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
# Since M8.3 the channel output must be one JSON object: append the notes self-check, keep the raw output in a side
# file, and print only the answer's last top-level JSON object (as cursor-review.sh does).
if [ -f "$prompt" ] && [ -f "$(dirname "$0")/review-addendum.md" ]; then
  merged=$(mktemp "${TMPDIR:-/tmp}/review-prompt.XXXXXX") && cat "$prompt" "$(dirname "$0")/review-addendum.md" > "$merged" && prompt=$merged
fi
mkdir -p "$REVIEWS/.transcripts"
side="$REVIEWS/.transcripts/claude-$(date +%Y%m%dT%H%M%S)-$$.log"
if [ -f "$prompt" ]; then claude -p "$@" < "$prompt" > "$side" 2>&1; else claude -p "$prompt" "$@" </dev/null > "$side" 2>&1; fi
rc=$?
python3 "$(dirname "$0")/last-json.py" < "$side"
exit $rc
