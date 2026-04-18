"""Scaffold specy-road kit directories into a target repository root."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from specy_road.runtime_paths import (
    default_user_repo_root,
    specy_road_package_dir,
)


def project_template_root() -> Path:
    return specy_road_package_dir() / "templates" / "project"


def run_init_project(
    target: Path | None,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """Copy bundled templates/project into target. Return exit code."""
    dst = (target or default_user_repo_root()).resolve()
    src = project_template_root()
    if not src.is_dir():
        print(f"error: missing project template at {src}", file=sys.stderr)
        return 2

    marker = dst / "roadmap" / "manifest.json"
    if marker.is_file() and not force:
        msg = (
            f"error: {marker} already exists. "
            "Use --force to overwrite scaffold files."
        )
        print(msg, file=sys.stderr)
        return 1

    written: list[str] = []
    skipped: list[str] = []
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        out = dst / rel
        if out.exists() and not force:
            skipped.append(str(rel))
            continue
        if dry_run:
            print(f"would write {out}")
            written.append(str(rel))
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
        written.append(str(rel))

    if dry_run:
        print(f"dry-run: {len(written)} file(s) would be written under {dst}")
        if skipped:
            print(f"dry-run: would skip {len(skipped)} existing (no --force)")
        return 0

    for rel in written:
        print(f"wrote {rel}")
    for rel in skipped:
        print(f"skipped (exists): {rel}")
    print(f"Initialized specy-road layout under {dst}")
    return 0
