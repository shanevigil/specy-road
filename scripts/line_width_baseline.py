#!/usr/bin/env python3
"""Lines over 100 characters per file, against scripts/line_width_baseline.json.

A report, never a gate: ``python scripts/lean_metrics.py --check`` prints each
file whose count rose or that is outside the baseline, and the total against
it; no test or CI step fails on a width count. Counts come from
``ruff check --select E501 --line-length 100 --output-format json`` over
specy_road, scripts and tests, so a ``noqa: E501`` line is not counted.

Usage:
    python scripts/line_width_baseline.py                     # write the baseline
    python scripts/line_width_baseline.py --transfer OLD NEW  # move OLD's count onto NEW

The baseline is the count at M16.1.8's pickup. A leaf that moves or folds a
file and records it as OLD -> NEW runs ``--transfer OLD NEW``; a fold adds
OLD's count to NEW's. A fold leaf that rewraps the files it merges lowers their
entries by hand. Only maintainers rewrite the whole file.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "scripts" / "line_width_baseline.json"
AREAS = ("specy_road", "scripts", "tests")
RUFF = ("ruff", "check", "--no-cache", "--select", "E501", "--line-length", "100",
        "--output-format", "json")


def counts(root: Path = REPO) -> dict[str, int]:
    """``{path: lines over 100 characters}`` under ``root``'s areas; files with none are left out.

    Ruff exits 1 when it finds any, so the exit is not checked.
    """
    proc = subprocess.run([*RUFF, *AREAS], cwd=root, capture_output=True, text=True, check=False)
    found = Counter(
        Path(f["filename"]).resolve().relative_to(root.resolve()).as_posix()
        for f in json.loads(proc.stdout)
    )
    return dict(sorted(found.items()))


def transfer(files: dict[str, int], old: str, new: str) -> dict[str, int]:
    """``files`` with OLD's count moved onto NEW (added to NEW's own count after a fold)."""
    moved = dict(files)
    count = moved.pop(old, 0)
    if count:
        moved[new] = moved.get(new, 0) + count
    return dict(sorted(moved.items()))


def report(baseline: dict[str, int], current: dict[str, int]) -> list[str]:
    """One line per file whose count rose or that is outside the baseline, then the total."""
    lines = []
    for rel, now in current.items():
        if rel not in baseline:
            lines.append(f"  {rel}: {now} (not in the baseline)")
        elif now > baseline[rel]:
            lines.append(f"  {rel}: {baseline[rel]} -> {now} (+{now - baseline[rel]})")
    before, after = sum(baseline.values()), sum(current.values())
    lines.append(f"  total: {before} -> {after} ({after - before:+d})")
    return lines


def load() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def write(data: dict) -> None:
    BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--transfer", nargs=2, metavar=("OLD", "NEW"),
                        help="move OLD's count onto NEW for a recorded move or fold")
    args = parser.parse_args(argv)

    if args.transfer:
        old, new = args.transfer
        data = load()
        count = data["files"].get(old, 0)
        data["files"] = transfer(data["files"], old, new)
        write(data)
        print(f"moved {count} lines over 100 characters from {old} to {new}")
        return 0
    ruff = subprocess.run(["ruff", "--version"], capture_output=True, text=True, check=False)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                            text=True, check=True).stdout.strip()
    files = counts()
    write({
        "command": " ".join([*RUFF, *AREAS]),
        "ruff": ruff.stdout.strip(),
        "commit": commit,
        "files": files,
    })
    print(f"wrote {BASELINE.relative_to(REPO)}: {sum(files.values())} lines in {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
