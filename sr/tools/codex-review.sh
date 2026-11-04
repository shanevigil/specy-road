#!/bin/sh
# codex-review.sh <codex model id> <prompt text | prompt file> [effort]: one reviewer turn on the Codex CLI.
# A prompt file (the roster's {prompt}) goes in on stdin: Linux caps one argument at 128 KiB.
# Runs in the current worktree; the main checkout's sr/work/reviews ($REVIEWS, from env.sh) is added as a writable dir
# so the reviewer can write its REVIEW and notes files there. effort (low|medium|high) overrides
# the Codex config's model_reasoning_effort.
model=$1 prompt=$2 effort=$3
. "$(dirname "$0")/env.sh"
set -- -m "$model" ${effort:+-c model_reasoning_effort="$effort"} -s workspace-write --add-dir "$REVIEWS" --skip-git-repo-check
if [ -f "$prompt" ]; then exec codex exec "$@" - < "$prompt"; fi
exec codex exec "$@" "$prompt" </dev/null
