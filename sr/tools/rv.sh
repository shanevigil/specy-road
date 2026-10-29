#!/usr/bin/env bash
# Review one leaf: trial-merge with WIP, rebuild the packet, then Grok; Sol only after Grok approves.
# Usage: sr/tools/rv.sh <NODE_ID> <worktree-dir-name>
set -u
ID=$1; WT=$2
ROOT=/Users/savigil/WORKSPACE/specy-road; S=$ROOT/sr/tools/specy-road; LOG=$ROOT/work/grind-logs; mkdir -p "$LOG"
cd "$ROOT" || exit 2
git fetch -q origin WIP/improvements-0-3-1 2>/dev/null
B=$(git -C "sr/work/.worktrees/$WT" branch --show-current)
if ! git -C "sr/work/.worktrees/$WT" merge-tree --write-tree --name-only origin/WIP/improvements-0-3-1 HEAD >/dev/null 2>&1; then
  echo "$ID: MERGE CONFLICT with WIP"; exit 3; fi
$S review-packet "$ID" --ref "$B" >/dev/null 2>&1
Z=$(grep 'outside touch zones\*\*' "sr/work/reviews/$ID/PACKET.md" | sed 's/  \*\*.*//')
if [ -n "$Z" ]; then echo "$ID: OUT OF ZONE: $Z"; exit 4; fi
cd "sr/work/.worktrees/$WT/sr" || exit 2
$S prompt "$ID" --role reviewer --model ${R1:-cursor-grok-4.6-high} --channel cli --repo-root "$PWD" > "$LOG/$ID-r1.log" 2>&1
cd "$ROOT"
V=$(grep -m1 '^verdict' "sr/work/reviews/$ID/REVIEW-${R1:-cursor-grok-4.6-high}.md" 2>/dev/null | awk '{print $2}')
if [ "$V" != "approve" ]; then echo "$ID: grok ${V:-no-record}"; exit 5; fi
cd "sr/work/.worktrees/$WT/sr" || exit 2
$S prompt "$ID" --role reviewer --model ${R2:-gpt-6.1-sol} --channel cli --repo-root "$PWD" > "$LOG/$ID-r2.log" 2>&1
cd "$ROOT"
$S handoff status "$ID" 2>&1 | grep -E "policy" | sed "s/^/$ID: /"
