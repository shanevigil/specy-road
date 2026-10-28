#!/usr/bin/env python3
"""Fail on duplicate-code clone pairs that are not in the committed baseline.

Runs pylint's R0801 (duplicate-code) checker over the source tree, reduces each
reported clone to a canonical key (sorted module names plus duplicated line
count), and compares that set with ``constraints/clone-baseline.json``.

Any clone pair absent from the baseline fails the gate. Pairs that disappeared
are reported as stale so the baseline can be shrunk with ``--update-baseline``.

Usage:
    python scripts/check_clones.py                 # gate
    python scripts/check_clones.py --update-baseline
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

MIN_SIMILARITY_LINES = 6
R0801_RE = re.compile(r"R0801: Similar lines in (\d+) files")
RANGE_RE = re.compile(r"^==(?P<module>\S+):\[(?P<start>\d+):(?P<end>\d+)\]$")
# pylint exit status bits that mean "pylint itself failed", not "findings".
PYLINT_FATAL_BITS = 1 | 32


def pylint_args(source: Path, pylint: str) -> list[str]:
    return [
        pylint,
        "--disable=all",
        "--enable=duplicate-code",
        f"--min-similarity-lines={MIN_SIMILARITY_LINES}",
        "--ignore-imports=y",
        "--ignore-docstrings=y",
        "--ignore-signatures=y",
        "--score=n",
        source.name,
    ]


def run_pylint(source: Path, pylint: str) -> str:
    """Run pylint from the source's parent so module names are repo-relative."""
    proc = subprocess.run(
        pylint_args(source, pylint),
        cwd=source.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode & PYLINT_FATAL_BITS:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"pylint failed with status {proc.returncode}")
    return proc.stdout


def parse_clones(output: str) -> set[tuple[str, ...]]:
    """Return canonical keys: (module_a, module_b, ..., "<lines>")."""
    clones: set[tuple[str, ...]] = set()
    modules: list[str] = []
    lines = 0
    in_block = False

    def flush() -> None:
        if in_block and modules:
            clones.add((*sorted(modules), str(lines)))

    for raw in output.splitlines():
        if R0801_RE.search(raw):
            flush()
            modules, lines, in_block = [], 0, True
            continue
        match = RANGE_RE.match(raw.strip())
        if match and in_block:
            modules.append(match.group("module"))
            lines = max(lines, int(match.group("end")) - int(match.group("start")))
    flush()
    return clones


def load_baseline(path: Path) -> set[tuple[str, ...]]:
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {(*entry["modules"], str(entry["lines"])) for entry in data["clones"]}


def write_baseline(path: Path, clones: set[tuple[str, ...]]) -> None:
    entries = [{"modules": list(key[:-1]), "lines": int(key[-1])} for key in sorted(clones)]
    data = {
        "generated": date.today().isoformat(),
        "tool": "pylint duplicate-code (R0801)",
        "min_similarity_lines": MIN_SIMILARITY_LINES,
        "clones": entries,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def describe(key: tuple[str, ...]) -> str:
    return f"{' <-> '.join(key[:-1])} ({key[-1]} lines)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default="specy_road", type=Path)
    parser.add_argument("--baseline", default=Path("constraints/clone-baseline.json"), type=Path)
    parser.add_argument("--pylint", default="pylint", help="pylint executable")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)

    current = parse_clones(run_pylint(args.source.resolve(), args.pylint))
    if args.update_baseline:
        write_baseline(args.baseline, current)
        print(f"wrote {len(current)} clone pair(s) to {args.baseline}")
        return 0

    baseline = load_baseline(args.baseline)
    new = sorted(current - baseline)
    stale = sorted(baseline - current)
    print(f"clone pairs: {len(current)} current, {len(baseline)} baselined, {len(new)} new")
    for key in stale:
        print(f"  stale baseline entry (no longer detected): {describe(key)}")
    for key in new:
        print(f"  NEW CLONE: {describe(key)}")
    if new:
        print("Remove the duplication, or if it is intentional run: "
              "python scripts/check_clones.py --update-baseline")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
