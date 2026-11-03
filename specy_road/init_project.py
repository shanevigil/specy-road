"""Scaffold specy-road kit directories into a target repository root."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from specy_road.agents_md_block import apply_agents_md_block
from specy_road.managed_block import UNCHANGED
from specy_road.model_profiles import PROFILES_REL
from specy_road.runtime_paths import (
    git_root,
    prefix_within,
    project_root,
    specy_road_package_dir,
)


_GITIGNORE = Path(".gitignore")
_PROFILES_ALWAYS = frozenset({"README.md", "harness-facts.yaml"})


@dataclass(frozen=True)
class InitProfilesSelection:
    mode: str  # all | none | subset
    tokens: frozenset[str] = frozenset()


def bundled_profiles_template_dir() -> Path:
    return project_template_root() / PROFILES_REL


def index_bundled_profile_names(src_dir: Path) -> tuple[frozenset[str], frozenset[str], dict[str, str]]:
    """Family directory names, profile ``api_id`` stems, and ``api_id`` → path under ``model-profiles/``."""
    families: set[str] = set()
    api_ids: set[str] = set()
    rel_by_api: dict[str, str] = {}
    for src in src_dir.rglob("*.md"):
        if src.name == "README.md":
            continue
        rel_in = src.relative_to(src_dir).as_posix()
        parts = Path(rel_in).parts
        if len(parts) < 2:
            continue
        families.add(parts[0])
        api_id = Path(rel_in).stem
        api_ids.add(api_id)
        rel_by_api[api_id] = rel_in
    return frozenset(families), frozenset(api_ids), rel_by_api


def parse_init_profiles_spec(spec: str) -> InitProfilesSelection:
    raw = spec.strip()
    lower = raw.lower()
    if lower == "all":
        return InitProfilesSelection("all")
    if lower == "none":
        return InitProfilesSelection("none")
    tokens = frozenset(t.strip() for t in raw.split(",") if t.strip())
    if not tokens:
        raise ValueError("--profiles needs all, none, or a comma-separated list of family or api_id names")
    return InitProfilesSelection("subset", tokens)


def validate_init_profiles_selection(selection: InitProfilesSelection, src_dir: Path) -> None:
    if selection.mode != "subset":
        return
    families, api_ids, _ = index_bundled_profile_names(src_dir)
    unknown = selection.tokens - families - api_ids
    if unknown:
        raise ValueError(f"unknown profile name(s): {', '.join(sorted(unknown))}")


def include_template_profiles_file(rel: Path, selection: InitProfilesSelection) -> bool:
    """Whether ``init project`` should copy ``rel`` when it lives under ``model-profiles/``."""
    if not rel.parts or rel.parts[0] != PROFILES_REL.as_posix():
        return True
    rel_in = Path(*rel.parts[1:])
    rel_posix = rel_in.as_posix()
    if rel_posix in _PROFILES_ALWAYS or rel_in.name in _PROFILES_ALWAYS:
        return True
    if selection.mode == "all":
        return True
    if selection.mode == "none":
        return False
    if rel_in.suffix != ".md":
        return False
    parts = rel_in.parts
    if len(parts) < 2:
        return False
    return parts[0] in selection.tokens or rel_in.stem in selection.tokens


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


def run_init_project(  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
    target: Path | None,
    *,
    dry_run: bool = False,
    force: bool = False,
    profiles: str = "all",
) -> int:
    """Copy bundled templates/project into target. Return exit code."""
    dst = project_root(target) if target else project_root()
    src = project_template_root()
    if not src.is_dir():
        print(f"error: missing project template at {src}", file=sys.stderr)
        return 2

    try:
        profile_selection = parse_init_profiles_spec(profiles)
        profiles_src = bundled_profiles_template_dir()
        if profiles_src.is_dir():
            validate_init_profiles_selection(profile_selection, profiles_src)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    marker = dst / "roadmap" / "manifest.json"
    if marker.is_file() and not force:
        msg = (
            f"error: {marker} already exists. To upgrade this repo, run "
            "specy-road refresh-schemas, refresh-profiles and refresh-stubs instead. "
            "--force overwrites every scaffold file: roadmap/, planning/, "
            "constitution/, schemas/, model-profiles/ and the rest."
        )
        print(msg, file=sys.stderr)
        return 1

    written: list[str] = []
    skipped: list[str] = []
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        if not include_template_profiles_file(rel, profile_selection):
            continue
        out = dst / rel
        # .gitignore is the consumer's even under --force; its managed block is
        # re-applied by _record_layout below.
        if out.exists() and (not force or rel == _GITIGNORE):
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
        outcome = apply_agents_md_block(dst, dry_run=True)
        if outcome != UNCHANGED:
            print(f"would write AGENTS.md ({outcome})")
        print(f"dry-run: {len(written)} file(s) would be written under {dst}")
        if skipped:
            print(f"dry-run: would skip {len(skipped)} existing (no --force)")
        return 0

    # AGENTS.md is a managed block, not a template file: an existing file gets
    # the section inserted, with or without --force. Every other existing
    # scaffold file except .gitignore was replaced above when --force was given.
    outcome = apply_agents_md_block(dst)
    if outcome != UNCHANGED:
        written.append(f"AGENTS.md ({outcome})")
    for rel in written:
        print(f"wrote {rel}")
    for rel in skipped:
        print(f"skipped (exists): {rel}")
    recorded = _record_layout(dst)
    print(f"Initialized specy-road layout under {dst}")
    if recorded and recorded != ".":
        print(f"Recorded project_root={recorded} in .specyrd/manifest.json")
    return 0
