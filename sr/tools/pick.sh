#!/usr/bin/env bash
# Pick up a leaf into its own worktree and delegate it.
# Usage: sr/tools/pick.sh <NODE_ID> <worktree-dir-name> [model] [harness]
set -u
ID=$1; WT=$2; M=${3:-composer-2.5}; H=${4:-cursor}
ROOT=/Users/savigil/WORKSPACE/specy-road; S=$ROOT/sr/tools/specy-road
cd "$ROOT" || exit 2
$S do-next-available-task --under "$ID" >/dev/null 2>&1
B=$(git branch --show-current)
rm -f "sr/work/brief-$ID.md"
git checkout -q WIP/improvements-0-3-1
case "$B" in feature/rm-*) ;; *) echo "$ID: pickup failed (on $B)"; exit 3;; esac
git worktree add -q "sr/work/.worktrees/$WT" "$B" || exit 4
$S worker delegate "$ID" --model "$M" --harness "$H" --worktree "sr/work/.worktrees/$WT" 2>&1 | tail -1
$S worker list 2>&1 | awk -v id="$ID" '$2==id{print "worker:", $1}'
