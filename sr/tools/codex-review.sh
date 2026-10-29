#!/bin/sh
# codex-review.sh <codex model id> <prompt text>: one reviewer turn on the Codex CLI.
# Runs in the current worktree; the main checkout's sr/work/reviews is added as a writable dir
# so the reviewer can write its REVIEW and notes files there.
model=$1 prompt=$2
PATH=/Users/savigil/WORKSPACE/specy-road/sr/tools:$PATH
export PATH
exec codex exec -m "$model" -s workspace-write \
  --add-dir /Users/savigil/WORKSPACE/specy-road/sr/work/reviews \
  --skip-git-repo-check "$prompt"
