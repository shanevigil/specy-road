"""Per-test coverage overlap from a ``--cov-context=test`` run (census measurements 2 and 3).

Reads ``.coverage`` (coverage.py SQLite DB with dynamic test contexts) and prints:

* ``round``  -- for every test in the review-round files: the share of its covered
                (file, line) set also covered by a test outside those files; per file
                the test count, median overlap, fold candidates (>= 95 %) and tests with
                unique lines; then each fold candidate with its best non-round twin.
* ``unique`` -- tests with zero uniquely covered lines, grouped by test file (top N).

Usage: ``python scripts/census/coverage_overlap.py round|unique [.coverage] [--top 15]``.
Needs the ``coverage`` package from the venv that produced the DB.
"""

from __future__ import annotations

import fnmatch
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from coverage import CoverageData

ROUND_PATTERNS = (
    "tests/test_worker_review_round1.py", "tests/test_worker_review_round2.py",
    "tests/test_review_round2_routing.py", "tests/test_review_round4_sol.py",
    "tests/test_review_round4_sol_b.py", "tests/test_review_round5.py",
    "tests/test_review_round6_*.py", "tests/test_worker_faults.py",
)


def load(db: str) -> dict[str, set[tuple[str, int]]]:
    """Map test id (``file::name[params]``) to the set of (file, line) it executed."""
    data = CoverageData(db)
    data.read()
    cov: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for f in data.measured_files():
        rel = str(Path(f).relative_to(Path.cwd())) if f.startswith(str(Path.cwd())) else f
        for line, ctxs in data.contexts_by_lineno(f).items():
            for c in ctxs:
                if not c:
                    continue  # the empty context is collection/import time
                tid = c.split("|", 1)[0]  # strip |setup / |call / |teardown
                cov[tid].add((rel, line))
    return cov


def is_round(tid: str) -> bool:
    return any(fnmatch.fnmatch(tid.split("::", 1)[0], p) for p in ROUND_PATTERNS)


def cmd_round(cov: dict[str, set[tuple[str, int]]]) -> None:
    outside: set[tuple[str, int]] = set()
    for tid, lines in cov.items():
        if not is_round(tid):
            outside |= lines
    non_round = {t: ls for t, ls in cov.items() if not is_round(t)}
    per_file: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
    for tid, lines in cov.items():
        if not is_round(tid) or not lines:
            continue
        shared = len(lines & outside)
        per_file[tid.split("::", 1)[0]].append((tid, shared / len(lines), len(lines) - shared))
    print("| round file | tests | median overlap | fold candidates (>=95%) | keep (unique lines) |")
    print("|---|---:|---:|---:|---:|")
    folds: list[tuple[str, float, int]] = []
    for f in sorted(per_file):
        rows = per_file[f]
        fold = [r for r in rows if r[1] >= 0.95]
        keep = [r for r in rows if r[2] > 0]
        folds += fold
        print(f"| {f} | {len(rows)} | {statistics.median(r[1] for r in rows):.1%} | {len(fold)} | {len(keep)} |")
    print(f"\nFold candidates: {len(folds)}\n")
    print("| round test | overlap | unique lines | best non-round twin | twin covers |")
    print("|---|---:|---:|---|---:|")
    for tid, ov, uniq in sorted(folds, key=lambda r: (-r[1], r[0])):
        mine = cov[tid]
        best, best_n = "", 0
        for other, lines in non_round.items():
            n = len(mine & lines)
            if n > best_n:
                best, best_n = other, n
        print(f"| `{tid}` | {ov:.1%} | {uniq} | `{best}` | {best_n / len(mine):.0%} |")


def cmd_unique(cov: dict[str, set[tuple[str, int]]], top: int) -> None:
    owners: dict[tuple[str, int], int] = defaultdict(int)
    for lines in cov.values():
        for ln in lines:
            owners[ln] += 1
    zero_by_file: dict[str, int] = defaultdict(int)
    total_by_file: dict[str, int] = defaultdict(int)
    zero = 0
    for tid, lines in cov.items():
        f = tid.split("::", 1)[0]
        total_by_file[f] += 1
        if not any(owners[ln] == 1 for ln in lines):
            zero += 1
            zero_by_file[f] += 1
    print(f"Tests with coverage data: {len(cov)}; with zero unique lines: {zero} ({zero / len(cov):.0%})\n")
    print("| test file | tests | zero-unique | share |")
    print("|---|---:|---:|---:|")
    for f, n in sorted(zero_by_file.items(), key=lambda kv: -kv[1])[:top]:
        print(f"| {f} | {total_by_file[f]} | {n} | {n / total_by_file[f]:.0%} |")


def main(argv: list[str]) -> int:
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 15
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--top")]
    cmd = args[0] if args else "round"
    cov = load(args[1] if len(args) > 1 else ".coverage")
    (cmd_round(cov) if cmd == "round" else cmd_unique(cov, top))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
