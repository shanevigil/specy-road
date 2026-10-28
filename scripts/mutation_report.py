#!/usr/bin/env python3
"""Per-module mutation score table from ``mutmut results --all true`` output.

mutmut 3 prints one line per mutant: ``    <module>.<mangled func>__mutmut_N: <status>``.
This script groups those lines by module, prints a Markdown table, and (when a
baseline exists) fails if any module's score dropped by more than
``--max-drop`` points. There is deliberately no global floor.

Score = 100 * killed / (killed + survived), where "killed" also counts
``timeout`` and ``caught by type check`` and the denominator ignores
``no tests``, ``skipped``, ``suspicious``, ``segfault`` and ``not checked``.

Usage:
    mutmut results --all true > mutmut-results.txt
    python scripts/mutation_report.py mutmut-results.txt \\
        --baseline constraints/mutation-baseline.json --output mutation-report.md
    python scripts/mutation_report.py mutmut-results.txt \\
        --write-baseline constraints/mutation-baseline.json   # seed / refresh
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

RESULT_RE = re.compile(r"^\s*(?P<name>\S+?__mutmut_\d+): (?P<status>.+?)\s*$")
KILLED = {"killed", "timeout", "caught by type check"}
SURVIVED = {"survived"}


def parse_results(text: str) -> dict[str, dict[str, int]]:
    """Map module -> {"killed": n, "survived": n, "other": n}."""
    per_module: dict[str, dict[str, int]] = defaultdict(lambda: {"killed": 0, "survived": 0, "other": 0})
    for line in text.splitlines():
        match = RESULT_RE.match(line)
        if not match:
            continue
        module = match.group("name").rsplit(".", 1)[0]
        status = match.group("status")
        bucket = "killed" if status in KILLED else "survived" if status in SURVIVED else "other"
        per_module[module][bucket] += 1
    return dict(per_module)


def score(counts: dict[str, int]) -> float | None:
    denominator = counts["killed"] + counts["survived"]
    if denominator == 0:
        return None
    return round(100.0 * counts["killed"] / denominator, 1)


def scores(per_module: dict[str, dict[str, int]]) -> dict[str, float]:
    return {m: s for m, c in per_module.items() if (s := score(c)) is not None}


def markdown_table(per_module: dict[str, dict[str, int]], baseline: dict[str, float]) -> str:
    rows = ["| Module | Killed | Survived | Other | Score | Baseline | Delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    totals = {"killed": 0, "survived": 0, "other": 0}
    for module in sorted(per_module):
        counts = per_module[module]
        for key in totals:
            totals[key] += counts[key]
        current = score(counts)
        base = baseline.get(module)
        delta = "" if current is None or base is None else f"{current - base:+.1f}"
        rows.append(
            f"| `{module}` | {counts['killed']} | {counts['survived']} | {counts['other']} | "
            f"{'n/a' if current is None else current} | {'' if base is None else base} | {delta} |"
        )
    total_score = score(totals)
    rows.append(
        f"| **total** | {totals['killed']} | {totals['survived']} | {totals['other']} | "
        f"{'n/a' if total_score is None else total_score} | | |"
    )
    return "\n".join(rows) + "\n"


def regressions(current: dict[str, float], baseline: dict[str, float], max_drop: float) -> list[str]:
    return [
        f"{module}: {baseline[module]} -> {current[module]} (drop {baseline[module] - current[module]:.1f} > {max_drop})"
        for module in sorted(current)
        if module in baseline and baseline[module] - current[module] > max_drop
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path, help="saved output of `mutmut results --all true`")
    parser.add_argument("--baseline", default=Path("constraints/mutation-baseline.json"), type=Path)
    parser.add_argument("--max-drop", default=2.0, type=float, help="points a module may drop")
    parser.add_argument("--output", type=Path, help="also write the Markdown table here")
    parser.add_argument("--write-baseline", type=Path, help="write per-module scores as JSON and exit")
    args = parser.parse_args(argv)

    per_module = parse_results(args.results.read_text(encoding="utf-8"))
    if not per_module:
        print("no mutant result lines found", file=sys.stderr)
        return 2
    current = scores(per_module)

    if args.write_baseline:
        payload = {"generated": date.today().isoformat(), "max_drop": args.max_drop, "modules": current}
        args.write_baseline.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {len(current)} module score(s) to {args.write_baseline}")
        return 0

    baseline: dict[str, float] = {}
    if args.baseline.is_file():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8")).get("modules", {})
    table = markdown_table(per_module, baseline)
    print(table)
    if args.output:
        args.output.write_text(table, encoding="utf-8")

    if not baseline:
        print(f"no baseline at {args.baseline}; report only (seed it with --write-baseline)")
        return 0
    dropped = regressions(current, baseline, args.max_drop)
    for line in dropped:
        print(f"MUTATION SCORE DROP: {line}")
    return 1 if dropped else 0


if __name__ == "__main__":
    sys.exit(main())
