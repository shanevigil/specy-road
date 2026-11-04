#!/usr/bin/env bash
# Land an approved leaf and free its slot. Usage: sr/tools/land.sh <NODE_ID> <worktree-dir-name> <worker-id>
set -u
# Coordinator pause: no new landings while /tmp/specy-pause exists.
if [ -e /tmp/specy-pause ]; then echo "$1: paused, not landing (rm /tmp/specy-pause to resume)"; exit 5; fi
ID=$1; WT=$2; W=$3
ROOT=/Users/savigil/WORKSPACE/specy-road; S=$ROOT/sr/tools/specy-road
cd "$ROOT" || exit 2
# Real conflicts only: finish-this-task resolves the generated bookkeeping files itself.
real_conflicts() { git -C "$1" merge-tree --write-tree --name-only origin/WIP/improvements-0-3-1 HEAD 2>/dev/null | sed -n '2,/^$/p' | grep -v -E '^$|^sr/roadmap/registry\.yaml$|^sr/roadmap-context\.md$|^sr/roadmap\.md$'; }
git fetch -q origin WIP/improvements-0-3-1 2>/dev/null
B=$(git -C "sr/work/.worktrees/$WT" branch --show-current)
C=$(real_conflicts "sr/work/.worktrees/$WT")
[ -z "$C" ] || { echo "$ID: MERGE CONFLICT, not landing:" $C; exit 3; }
# The branch may carry the scaffold sheet while WIP has the written one (sheets are
# authored on WIP by the coordinator); the merge keeps WIP's, so allow it only then.
if [ -z "${FINISH_ARGS:-}" ] && "$ROOT/.conda/bin/python" -c "
import json,glob,sys; from pathlib import Path
from specy_road.planning_scaffold_check import scaffold_sheet
for f in glob.glob('sr/roadmap/phases/*.json'):
    d=json.load(open(f)); ns=d['nodes'] if isinstance(d,dict) and 'nodes' in d else d
    for n in ns:
        if n.get('id')=='$ID': sys.exit(0 if scaffold_sheet(Path('sr'),n) is None else 1)
sys.exit(1)"; then FINISH_ARGS=--allow-scaffold-planning; fi
(cd "sr/work/.worktrees/$WT/sr" && $S mark-implementation-reviewed --yes >/dev/null 2>&1 && $S finish-this-task ${FINISH_ARGS:-} 2>&1 | tee "$ROOT/work/grind-logs/$ID-finish.log" | grep -E '^\[ok\] merged|^error|policy|re-review')
if ! git merge-base --is-ancestor "$B" WIP/improvements-0-3-1 && git fetch -q origin && ! git merge-base --is-ancestor "$B" origin/WIP/improvements-0-3-1; then
  # A leaf that adds a schema key cannot be finished by the installed specy-road, whose
  # bundled schema predates it: restore finish's partial bookkeeping and retry with the
  # branch's own code (the code that is landing).
  W_ROOT="$ROOT/sr/work/.worktrees/$WT"
  git -C "$W_ROOT" checkout -- sr/roadmap 2>/dev/null
  echo "$ID: retrying finish with the branch's own specy-road"
  (cd "$W_ROOT/sr" && PYTHONPATH="$W_ROOT" "$ROOT/.conda/bin/python" -m specy_road.cli mark-implementation-reviewed --yes >/dev/null 2>&1; PYTHONPATH="$W_ROOT" "$ROOT/.conda/bin/python" -m specy_road.cli finish-this-task ${FINISH_ARGS:-} 2>&1 | tee "$ROOT/work/grind-logs/$ID-finish-retry.log" | grep -E '^\[ok\] merged|^error')
  git fetch -q origin
  git merge-base --is-ancestor "$B" origin/WIP/improvements-0-3-1 || { echo "$ID: NOT MERGED"; exit 4; }
  git pull -q --ff-only origin WIP/improvements-0-3-1
fi
git worktree remove --force "sr/work/.worktrees/$WT" && git worktree prune
$S worker terminate "$W" >/dev/null 2>&1
echo "$ID landed; complete: $($S list-nodes 2>/dev/null | grep -cE 'task +Complete')"
