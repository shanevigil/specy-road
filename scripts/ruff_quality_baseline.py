#!/usr/bin/env python3
"""Ruff quality-rule families per file, against scripts/ruff_quality_baseline.json.

A report, never a gate: ``python scripts/lean_metrics.py --check`` names each
file whose count in a family rose or that is outside the baseline, then each
family's total and its delta from this file's commit. No test or CI step fails
on a family count. Counts come from ``ruff check --select <family>
--output-format json`` over specy_road, scripts and tests. C901 is counted with
``--ignore-noqa``, so a waiver is still a finding; the other families honour
noqa. The families are selected only here, so pyproject's ruff gate is unchanged.

Usage:
    python scripts/ruff_quality_baseline.py                     # write the baseline
    python scripts/ruff_quality_baseline.py --shrink            # lower entries, never raise
    python scripts/ruff_quality_baseline.py --transfer OLD NEW  # move OLD onto NEW

The baseline is the count at M16.1.11's pickup. A full rewrite counts the tree
of the commit it records (``git archive`` of that commit), not the worktree: a
file that is not in the commit, and a worktree edit of a file that is, stay out
of the baseline. A leaf that moves or folds a file and records it as OLD -> NEW
runs ``--transfer OLD NEW``; a fold adds OLD's count to NEW's, per family.
``--shrink`` rewrites an entry only when the current count is lower. A file that
is gone counts as zero and its entry is removed. A file or family that is not
already in the baseline is not added. Only maintainers rewrite the whole file.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "scripts" / "ruff_quality_baseline.json"
AREAS = ("specy_road", "scripts", "tests")
# Report name, then the ruff arguments that select that one family.
# C901 ignores noqa so a waiver is still counted; the others honour it.
FAMILIES = (
    ("C901", ("--select", "C901", "--ignore-noqa")),
    ("PL", ("--select", "PL")),
    ("B", ("--select", "B")),
    ("SIM", ("--select", "SIM")),
    ("RET", ("--select", "RET")),
    ("N", ("--select", "N")),
    ("D102/D103", ("--select", "D102,D103")),
)
FAMILY_NAMES = tuple(name for name, _extra in FAMILIES)


def ruff_command(extra: tuple[str, ...]) -> tuple[str, ...]:
    """``ruff check`` for one family, without the area paths."""
    return ("ruff", "check", "--no-cache", *extra, "--output-format", "json")


def counts(root: Path = REPO) -> dict[str, dict[str, int]]:
    """``{path: {family: findings}}`` under ``root``'s areas; a file with none is left out.

    Ruff exits 1 when it finds any, so the exit is not checked. One invocation
    per family, because C901 is the only select that passes ``--ignore-noqa``.
    """
    found: dict[str, dict[str, int]] = {}
    for name, extra in FAMILIES:
        proc = subprocess.run(
            [*ruff_command(extra), *AREAS],
            cwd=root, capture_output=True, text=True, check=False,
        )
        for item in json.loads(proc.stdout):
            rel = Path(item["filename"]).resolve().relative_to(root.resolve()).as_posix()
            per_file = found.setdefault(rel, {})
            per_file[name] = per_file.get(name, 0) + 1
    return {rel: _in_family_order(found[rel]) for rel in sorted(found)}


def counts_at(commit: str, root: Path = REPO) -> dict[str, dict[str, int]]:
    """Findings in ``commit``'s tree under the three areas. The worktree is not read."""
    proc = subprocess.run(
        ["git", "archive", "--format=tar", commit],
        cwd=root, capture_output=True, check=True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode="r:") as archive:
            archive.extractall(tmp)
        return counts(Path(tmp))


def _in_family_order(per_file: dict[str, int]) -> dict[str, int]:
    return {name: per_file[name] for name in FAMILY_NAMES if name in per_file}


def transfer(
    files: dict[str, dict[str, int]], old: str, new: str,
) -> dict[str, dict[str, int]]:
    """``files`` with OLD's per-family counts moved onto NEW (added after a fold)."""
    moved = {rel: dict(per_file) for rel, per_file in files.items()}
    taken = moved.pop(old, {})
    if taken:
        merged = dict(moved.get(new, {}))
        for name, count in taken.items():
            merged[name] = merged.get(name, 0) + count
        moved[new] = _in_family_order(merged)
    return dict(sorted(moved.items()))


def shrink(
    baseline: dict[str, dict[str, int]], current: dict[str, dict[str, int]],
) -> dict[str, dict[str, int]]:
    """Each stored count becomes ``min(stored, current)``. Nothing is added.

    A family missing from ``current`` is zero, and a zero count is dropped, so
    a file that is gone leaves the baseline. A higher current count is kept at
    the stored number.
    """
    lowered: dict[str, dict[str, int]] = {}
    for rel, per_file in baseline.items():
        now = current.get(rel, {})
        kept = {
            name: min(count, now.get(name, 0))
            for name, count in per_file.items()
            if min(count, now.get(name, 0))
        }
        if kept:
            lowered[rel] = _in_family_order(kept)
    return dict(sorted(lowered.items()))


def totals(files: dict[str, dict[str, int]]) -> dict[str, int]:
    """The sum of each family's counts, including a family with none."""
    sums = dict.fromkeys(FAMILY_NAMES, 0)
    for per_file in files.values():
        for name, count in per_file.items():
            if name in sums:
                sums[name] += count
    return sums


def report(
    baseline: dict[str, dict[str, int]], current: dict[str, dict[str, int]],
) -> list[str]:
    """One line per risen family or file outside the baseline, then each family's total."""
    lines = []
    for rel in sorted(current):
        now = current[rel]
        if rel not in baseline:
            body = ", ".join(f"{name} {now[name]}" for name in FAMILY_NAMES if now.get(name))
            lines.append(f"  {rel}: {body} (not in the baseline)")
            continue
        before = baseline[rel]
        for name in FAMILY_NAMES:
            old, new = before.get(name, 0), now.get(name, 0)
            if new > old:
                lines.append(f"  {rel} {name}: {old} -> {new} (+{new - old})")
    before_totals, after_totals = totals(baseline), totals(current)
    for name in FAMILY_NAMES:
        old, new = before_totals[name], after_totals[name]
        lines.append(f"  {name}: {old} -> {new} ({new - old:+d})")
    return lines


def load() -> dict:
    """The committed baseline."""
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def write(data: dict) -> None:
    """Rewrite the committed baseline."""
    BASELINE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Write the baseline, lower it with ``--shrink``, or move a file with ``--transfer``."""
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="A full rewrite counts the recorded commit's tree, not the worktree.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--shrink", action="store_true",
                      help="lower stored counts to the current ones and never raise one")
    mode.add_argument("--transfer", nargs=2, metavar=("OLD", "NEW"),
                      help="move OLD's per-family counts onto NEW for a recorded move or fold")
    args = parser.parse_args(argv)

    if args.shrink:
        data = load()
        updated = shrink(data["files"], counts())
        if updated == data["files"]:
            print("no entry lowered")
            return 0
        data["files"] = updated
        write(data)
        print("lowered entries")
        return 0
    if args.transfer:
        old, new = args.transfer
        data = load()
        taken = data["files"].get(old, {})
        data["files"] = transfer(data["files"], old, new)
        write(data)
        body = ", ".join(f"{name} {taken[name]}" for name in FAMILY_NAMES if taken.get(name))
        print(f"moved {body or 'nothing'} from {old} to {new}")
        return 0
    ruff = subprocess.run(["ruff", "--version"], capture_output=True, text=True, check=False)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.strip()
    files = counts_at(commit, REPO)
    write({
        "commands": {
            name: " ".join((*ruff_command(extra), *AREAS)) for name, extra in FAMILIES
        },
        "ruff": ruff.stdout.strip(),
        "commit": commit,
        "files": files,
    })
    findings = sum(totals(files).values())
    print(f"wrote {BASELINE.relative_to(REPO)}: {findings} findings in {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
