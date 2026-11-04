#!/usr/bin/env bash
# Review one leaf: trial-merge with WIP, rebuild the packet, then Grok; Sol only after Grok approves.
# Usage: sr/tools/rv.sh <NODE_ID> <worktree-dir-name>
set -u
ID=$1; WT=$2
. "$(dirname "$0")/env.sh"
S=$ROOT/sr/tools/specy-road; LOG=$ROOT/work/grind-logs; mkdir -p "$LOG"
cd "$ROOT" || exit 2
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
$S prompt "$ID" --role reviewer --model ${R1:-cursor-grok-4.6-high} --channel cli --repo-root "$PWD" > "$LOG/$ID-r1.log" 2>&1
cd "$ROOT"
V=$(grep -m1 '^verdict' "sr/work/reviews/$ID/REVIEW-${R1:-cursor-grok-4.6-high}.md" 2>/dev/null | awk '{print $2}')
if [ "$V" != "approve" ]; then echo "$ID: grok ${V:-no-record}"; exit 5; fi
cd "sr/work/.worktrees/$WT/sr" || exit 2
$S prompt "$ID" --role reviewer --model ${R2:-gpt-5.6-sol-high} --channel cli --repo-root "$PWD" > "$LOG/$ID-r2.log" 2>&1
cd "$ROOT"
$S handoff status "$ID" 2>&1 | grep -E "policy" | sed "s/^/$ID: /"
