#!/usr/bin/env python3
"""Print a leaf's review tier: plain, behavioural or trust (maintainer, 2026-11-09).

Usage: tier.py <NODE_ID> <worktree-dir>

The tier comes from the leaf's sheet as it is in the main checkout (the integration line), never from the
leaf's branch, so an executor cannot lower its own tier. A path floor then raises it:
  - a change to review, finish/land, worker launch/resume, secrets or network code is trust;
  - a change to any other Python file under specy_road/ is at least behavioural (built GUI assets do not count).
An unreadable sheet or diff counts as behavioural.
"""
import glob
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RANK = {"plain": 0, "behavioural": 1, "trust": 2}
TRUST = re.compile(r"^specy_road/(review_|finish|worker_(sandbox|runner|launch|resume)|harness_launch|"
                   r"secret|net|.*signing|.*policy_pin|bundled_scripts/review_cli)")


def sheet_tier(node: str) -> str:
    sheets = glob.glob(str(ROOT / "sr" / "planning" / f"{node}_*.md"))
    if not sheets:
        return "behavioural"
    m = re.search(r"^## Tier\s*\n+\s*([A-Za-z]+(?: boundary)?)", Path(sheets[0]).read_text(), re.M)
    if not m:
        return "behavioural"
    word = m.group(1).strip().lower()
    return "trust" if word.startswith("trust") else word if word in RANK else "behavioural"


def changed_paths(worktree: str) -> list[str] | None:
    def git(*a):
        return subprocess.run(["git", "-C", worktree, *a], capture_output=True, text=True)
    base = git("merge-base", "HEAD", "origin/WIP/improvements-0-3-1")
    if base.returncode:
        return None
    out = git("diff", "--name-only", base.stdout.strip(), "HEAD")
    return None if out.returncode else [p for p in out.stdout.splitlines() if p]


def tier(node: str, worktree: str) -> str:
    t = sheet_tier(node)
    paths = changed_paths(worktree)
    if paths is None:
        return max(t, "behavioural", key=RANK.get)
    if any(TRUST.match(p) for p in paths):
        return "trust"
    if any(p.startswith("specy_road/") and p.endswith(".py") for p in paths):
        return max(t, "behavioural", key=RANK.get)
    return t


if __name__ == "__main__":
    print(tier(sys.argv[1], sys.argv[2]))
