"""Scaffold specy-road kit directories into a target repository root."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from specy_road.runtime_paths import (
    git_root,
    prefix_within,
    project_root,
    specy_road_package_dir,
)


def project_template_root() -> Path:
    return specy_road_package_dir() / "templates" / "project"


def _record_layout(dst: Path) -> str | None:
    """Note in ``.specyrd/manifest.json`` where the project tree was put.

    ``init project sr`` has always scaffolded into a subfolder, but nothing
    remembered that it had, so every later command had to re-guess. Recording
    it is what makes the nested layout deterministic instead of discovered —
    a repository can hold two roadmaps, and a scan picks one of them silently.

    The ignore blocks are refreshed here too. They are written at the git root
    but name paths inside the project, so they need this prefix; rewriting them
    now means the two ``init`` commands can be run in either order without
    leaving an unprefixed block behind that matches nothing.
    """
    top = git_root(dst)
    if top is None:
        return None
    prefix = prefix_within(top, dst)
    from specy_road.agent_ignores import apply_agent_ignores
    from specy_road.specyrd_init import _load_manifest, _save_manifest

    manifest = _load_manifest(top)
    manifest["project_root"] = prefix.rstrip("/") or "."
    _save_manifest(top, manifest)
    if (top / ".cursorindexingignore").is_file() or (top / ".gitignore").is_file():
        apply_agent_ignores(top, prefix)
    return manifest["project_root"]


def run_init_project(
    target: Path | None,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    """Copy bundled templates/project into target. Return exit code."""
    dst = project_root(target) if target else project_root()
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
    recorded = _record_layout(dst)
    print(f"Initialized specy-road layout under {dst}")
    if recorded and recorded != ".":
        print(f"Recorded project_root={recorded} in .specyrd/manifest.json")
    return 0
