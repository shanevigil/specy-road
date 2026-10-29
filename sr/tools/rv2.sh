#!/usr/bin/env bash
# Run only the second (OpenAI, Codex) review for a leaf whose first review already approved.
# Usage: sr/tools/rv2.sh <NODE_ID> <worktree-dir-name>
set -u
ID=$1; WT=$2
ROOT=/Users/savigil/WORKSPACE/specy-road; S=$ROOT/sr/tools/specy-road; LOG=$ROOT/work/grind-logs
cd "$ROOT/sr/work/.worktrees/$WT/sr" || exit 2
$S prompt "$ID" --role reviewer --model ${R2:-gpt-6.1-sol} --channel cli --repo-root "$PWD" > "$LOG/$ID-r2.log" 2>&1
cd "$ROOT"
grep -q "at capacity" "$LOG/$ID-r2.log" && { echo "$ID: codex at capacity"; exit 6; }
$S handoff status "$ID" 2>&1 | grep -E "policy" | sed "s/^/$ID: /"
