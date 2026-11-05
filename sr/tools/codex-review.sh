#!/bin/sh
# codex-review.sh <codex model id> <prompt text | prompt file> [effort]: one reviewer turn on the Codex CLI.
# A prompt file (the roster's {prompt}) goes in on stdin: Linux caps one argument at 128 KiB.
# Runs in the current worktree; the main checkout's sr/work/reviews ($REVIEWS, from env.sh) is added as a writable dir
# so the reviewer can write its REVIEW and notes files there. effort (low|medium|high) overrides
# the Codex config's model_reasoning_effort.
# The channel output (stdout and stderr, merged by specy-road) is ONLY the agent's final message (codex -o): since
# M8.3, specy-road parses it as one JSON object, and codex's own transcript prints the final message twice around a
# "tokens used" footer. The full transcript is kept in $REVIEWS/.transcripts/ for debugging.
model=$1 prompt=$2 effort=$3
. "$(dirname "$0")/env.sh"
last=$(mktemp "${TMPDIR:-/tmp}/codex-last.XXXXXX") || exit 1
trap 'rm -f "$last"' EXIT
set -- -m "$model" ${effort:+-c model_reasoning_effort="$effort"} -s workspace-write --add-dir "$REVIEWS" --skip-git-repo-check -o "$last"
mkdir -p "$REVIEWS/.transcripts"
side="$REVIEWS/.transcripts/codex-$(date +%Y%m%dT%H%M%S)-$$.log"
if [ -f "$prompt" ]; then codex exec "$@" - < "$prompt" > "$side" 2>&1; else codex exec "$@" "$prompt" </dev/null > "$side" 2>&1; fi
rc=$?
cat "$last"
exit $rc
