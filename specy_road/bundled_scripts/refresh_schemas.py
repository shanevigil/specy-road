#!/usr/bin/env python3
"""Refresh a consumer repository's ``schemas/`` from the installed toolkit.

``init project`` copies the JSON schemas into the consumer repo and never
touches them again, so a repo scaffolded before a schema grew (``type: gate``,
``implementation_review``) rejects output that the current ``add-node``,
``set-gate-status``, and ``mark-implementation-reviewed`` legitimately produce.
The only command that looked like a fix was ``init project --force``, which
overwrites *every* template file — including ``roadmap/manifest.json`` and the
phase chunks — and would destroy the roadmap it was meant to repair.

This command touches ``schemas/`` and nothing else.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from specy_road.init_project import project_template_root
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root

SCHEMAS_DIRNAME = "schemas"


def bundled_schemas_dir() -> Path:
    return project_template_root() / SCHEMAS_DIRNAME


def _strip_descriptions(obj: object) -> object:
    """Recursively drop ``description`` keys.

    Drift that matters is structural — a missing enum value or property. Prose
    edits to a description are not drift, and comparing raw bytes would nag
    every consumer whose schema is functionally current.
    """
    if isinstance(obj, dict):
        return {
            k: _strip_descriptions(v)
            for k, v in obj.items()
            if k != "description"
        }
    if isinstance(obj, list):
        return [_strip_descriptions(v) for v in obj]
    return obj


def _load_comparable(path: Path) -> object | None:
    try:
        with path.open(encoding="utf-8") as f:
            return _strip_descriptions(json.load(f))
    except (OSError, json.JSONDecodeError):
        return None


def stale_schema_names(repo_root: Path) -> list[str]:
    """Consumer schema filenames that differ structurally from the bundled ones.

    Only files present in both are compared; a schema the consumer never had is
    not drift, and ``validate`` already fails loudly on a schema it needs and
    cannot find.
    """
    src_dir = bundled_schemas_dir()
    dst_dir = repo_root / SCHEMAS_DIRNAME
    if not src_dir.is_dir() or not dst_dir.is_dir():
        return []
    out: list[str] = []
    for src in sorted(src_dir.glob("*.json")):
        dst = dst_dir / src.name
        if not dst.is_file():
            continue
        bundled = _load_comparable(src)
        consumer = _load_comparable(dst)
        if bundled is None or consumer is None:
            continue
        if bundled != consumer:
            out.append(src.name)
    return out


def warn_if_schemas_stale(repo_root: Path) -> None:
    """Print a one-line warning per structurally stale schema. Never fatal."""
    for name in stale_schema_names(repo_root):
        print(
            f"schemas: warning — {SCHEMAS_DIRNAME}/{name} differs from the "
            "schema bundled with this specy-road version, so commands may emit "
            "fields your copy rejects. Run: specy-road refresh-schemas",
            file=sys.stderr,
        )


def refresh_schemas(repo_root: Path, *, dry_run: bool = False) -> list[str]:
    """Copy bundled schemas over the consumer's. Returns repo-relative paths written."""
    src_dir = bundled_schemas_dir()
    if not src_dir.is_dir():
        raise ValueError(f"missing bundled schemas at {src_dir}")
    dst_dir = repo_root / SCHEMAS_DIRNAME
    written: list[str] = []
    for src in sorted(src_dir.glob("*.json")):
        dst = dst_dir / src.name
        rel = f"{SCHEMAS_DIRNAME}/{src.name}"
        if dst.is_file() and _load_comparable(dst) == _load_comparable(src):
            if src.read_text(encoding="utf-8") == dst.read_text(encoding="utf-8"):
                continue
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        written.append(rel)
    return written


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="specy-road refresh-schemas",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_repo_root_arg(p)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written; do not modify files.",
    )
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    root = (args.repo_root or default_user_repo_root()).resolve()
    try:
        written = refresh_schemas(root, dry_run=args.dry_run)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    if not written:
        print(f"schemas/ already matches specy-road ({root})")
        return
    verb = "would write" if args.dry_run else "wrote"
    for rel in written:
        print(f"{verb} {rel}")
    if args.dry_run:
        print("\n(dry-run; no files written)")
        return
    print(
        "\nReview the diff and run specy-road validate. Schemas are the only "
        "files this command touches."
    )


if __name__ == "__main__":
    main()
