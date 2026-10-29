#!/usr/bin/env bash
# Land an approved leaf and free its slot. Usage: sr/tools/land.sh <NODE_ID> <worktree-dir-name> <worker-id>
set -u
ID=$1; WT=$2; W=$3
ROOT=/Users/savigil/WORKSPACE/specy-road; S=$ROOT/sr/tools/specy-road
cd "$ROOT" || exit 2
git fetch -q origin WIP/improvements-0-3-1 2>/dev/null
B=$(git -C "sr/work/.worktrees/$WT" branch --show-current)
git -C "sr/work/.worktrees/$WT" merge-tree --write-tree --name-only origin/WIP/improvements-0-3-1 HEAD >/dev/null 2>&1 || { echo "$ID: MERGE CONFLICT, not landing"; exit 3; }
(cd "sr/work/.worktrees/$WT/sr" && $S mark-implementation-reviewed --yes >/dev/null 2>&1 && $S finish-this-task 2>&1 | grep -E '^\[ok\] merged|^error')
git merge-base --is-ancestor "$B" WIP/improvements-0-3-1 || { echo "$ID: NOT MERGED"; exit 4; }
git worktree remove --force "sr/work/.worktrees/$WT" && git worktree prune
$S worker terminate "$W" >/dev/null 2>&1
echo "$ID landed; complete: $($S list-nodes 2>/dev/null | grep -cE 'task +Complete')"
