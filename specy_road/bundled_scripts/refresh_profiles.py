#!/usr/bin/env python3
"""Add the model profiles this specy-road version ships that a repo lacks.

``init project`` scaffolds ``model-profiles/`` once, so a repo scaffolded by an
older version has none, and a repo whose roster names a model profiled only by
a newer version lacks that one file. This copies **missing** profiles and the
README, and never overwrites: the adopter's copies are theirs to edit (prices,
CLI syntax, their own research), which is why the profiles are scaffolded
rather than read from the package. Use ``--force`` for one named profile to
take the toolkit's copy over yours.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from specy_road.init_project import project_template_root
from specy_road.model_profiles import PROFILES_REL
from specy_road.runtime_paths import add_repo_root_arg, default_user_repo_root


def bundled_profiles_dir() -> Path:
    return project_template_root() / PROFILES_REL


def refresh_profiles(
    repo_root: Path, *, dry_run: bool = False, force: list[str] | None = None
) -> tuple[list[str], list[str]]:
    """``(written, kept)`` repo-relative paths. ``force`` names relative paths to overwrite."""
    src_dir = bundled_profiles_dir()
    if not src_dir.is_dir():
        raise ValueError(f"missing bundled model profiles at {src_dir}")
    dst_dir = repo_root / PROFILES_REL
    forced = {Path(f).as_posix() for f in force or []}
    written: list[str] = []
    kept: list[str] = []
    for src in sorted(p for p in src_dir.rglob("*.md")):
        rel_in = src.relative_to(src_dir).as_posix()
        rel = f"{PROFILES_REL.as_posix()}/{rel_in}"
        dst = dst_dir / rel_in
        if dst.is_file() and rel not in forced and rel_in not in forced:
            kept.append(rel)
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        written.append(rel)
    return written, kept


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="specy-road refresh-profiles",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_repo_root_arg(p)
    p.add_argument("--dry-run", action="store_true", help="Print what would be written; do not modify files.")
    p.add_argument(
        "--force", action="append", default=[], metavar="PATH",
        help="Overwrite this profile (repo-relative, e.g. model-profiles/openai-gpt/gpt-6.1-sol.md); repeatable.",
    )
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    root = (args.repo_root or default_user_repo_root()).resolve()
    try:
        written, kept = refresh_profiles(root, dry_run=args.dry_run, force=args.force)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    verb = "would write" if args.dry_run else "wrote"
    for rel in written:
        print(f"{verb} {rel}")
    if not written:
        print(f"model-profiles/ already has every profile this specy-road ships ({root})")
    elif kept:
        print(f"kept {len(kept)} existing profile(s); pass --force <path> to replace one")
    if written and not args.dry_run:
        print("Next: add roster entries with `profile:` in roadmap/orchestration.yaml, then `specy-road models list`.")


if __name__ == "__main__":
    main()
