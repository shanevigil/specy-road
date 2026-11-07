#!/usr/bin/env bash
# Review one leaf: trial-merge with WIP, rebuild the packet, then Grok; Sol only after Grok approves.
# Usage: sr/tools/rv.sh <NODE_ID> <worktree-dir-name>
set -u
ID=$1; WT=$2
. "$(dirname "$0")/env.sh"
S=$ROOT/sr/tools/specy-road; LOG=$ROOT/work/grind-logs; mkdir -p "$LOG"
cd "$ROOT" || exit 2
# One reviewer turn; since M8.3 a refused one-shot record ("rerun requested") gets one automatic retry.
# A landing rewrites the checkout the reviewer's tooling imports from; an ImportError mid-run is that race, not
# the leaf: wait for the coordinator's git lock (held for the whole landing) and run the reviewer once more.
LOCK=$ROOT/sr/work/orchestrator-2026-11-04/git.lock
review_once() { $S prompt "$ID" --role reviewer --model "$1" --channel cli --run --repo-root "$PWD" > "$2" 2>&1
  if grep -qE "cannot import name|ImportError|ModuleNotFoundError" "$2"; then
    echo "--- retry after an import error (a landing was rewriting the checkout) ---" >> "$2"
    [ -e "$LOCK" ] && flock "$LOCK" true; sleep 10
    $S prompt "$ID" --role reviewer --model "$1" --channel cli --run --repo-root "$PWD" >> "$2" 2>&1
  elif grep -q "rerun requested" "$2"; then echo "--- retry after a refused record ---" >> "$2"
    $S prompt "$ID" --role reviewer --model "$1" --channel cli --run --repo-root "$PWD" >> "$2" 2>&1; fi; }
# Real conflicts only: finish-this-task resolves the generated bookkeeping files itself.
real_conflicts() { git -C "$1" merge-tree --write-tree --name-only origin/WIP/improvements-0-3-1 HEAD 2>/dev/null | sed -n '2,/^$/p' | grep -v -E '^$|^sr/roadmap/registry\.yaml$|^sr/roadmap-context\.md$|^sr/roadmap\.md$'; }
git fetch -q origin WIP/improvements-0-3-1 2>/dev/null
B=$(git -C "sr/work/.worktrees/$WT" branch --show-current)
C=$(real_conflicts "sr/work/.worktrees/$WT")
if [ -n "$C" ]; then echo "$ID: MERGE CONFLICT with WIP:" $C; exit 3; fi
$S review-packet "$ID" --ref "$B" >/dev/null 2>&1
Z=$(grep '^- `.*outside touch zones\*\*' "sr/work/reviews/$ID/PACKET.md" | sed 's/  \*\*.*//')
if [ -n "$Z" ]; then echo "$ID: OUT OF ZONE: $Z"; exit 4; fi
cd "sr/work/.worktrees/$WT/sr" || exit 2
review_once "${R1:-cursor-grok-4.6-high}" "$LOG/$ID-r1.log"
cd "$ROOT"
V=$(grep -m1 '^verdict' "sr/work/reviews/$ID/REVIEW-${R1:-cursor-grok-4.6-high}.md" 2>/dev/null | awk '{print $2}')
if [ "$V" != "approve" ]; then echo "$ID: ${R1:-cursor-grok-4.6-high} ${V:-no-record}"; exit 5; fi
cd "sr/work/.worktrees/$WT/sr" || exit 2
review_once "${R2:-gpt-5.6-sol-high}" "$LOG/$ID-r2.log"
cd "$ROOT"
$S handoff status "$ID" 2>&1 | grep -E "policy" | sed "s/^/$ID: /"
