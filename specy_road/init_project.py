"""Scaffold specy-road kit directories into a target repository root."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from specy_road.agents_md_block import apply_agents_md_block
from specy_road.managed_block import UNCHANGED
from specy_road.model_profiles import PROFILES_REL, load_profile
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
    profile_rels: frozenset[str] = frozenset()


def bundled_profiles_template_dir() -> Path:
    return project_template_root() / PROFILES_REL


def index_bundled_profile_names(
    src_dir: Path,
) -> tuple[frozenset[str], frozenset[str], dict[str, tuple[str, ...]]]:
    """Family directory names, file stems and front-matter ``api_id`` values, and token → rels.

    A token matches the same names ``Profile.api_id`` / ``Profile.for_id`` use (front-matter
    ``api_id``, else the file stem) plus the file stem itself. One ``api_id`` can name several files.
    """
    families: set[str] = set()
    rels_by_token: dict[str, list[str]] = {}

    def add(token: str, rel: str) -> None:
        bucket = rels_by_token.setdefault(token, [])
        if rel not in bucket:
            bucket.append(rel)

    for src in sorted(p for p in src_dir.rglob("*.md") if p.name != "README.md"):
        rel_in = src.relative_to(src_dir).as_posix()
        parts = Path(rel_in).parts
        if len(parts) < 2:
            continue
        families.add(parts[0])
        add(parts[0], rel_in)
        add(Path(rel_in).stem, rel_in)
        add(load_profile(src).api_id, rel_in)
    family_set = frozenset(families)
    return (
        family_set,
        frozenset(k for k in rels_by_token if k not in family_set),
        {k: tuple(v) for k, v in rels_by_token.items()},
    )


def parse_init_profiles_spec(spec: str) -> InitProfilesSelection:
    raw = spec.strip()
    lower = raw.lower()
    if lower == "all":
        return InitProfilesSelection("all")
    if lower == "none":
        return InitProfilesSelection("none")
    tokens = frozenset(t.strip() for t in raw.split(",") if t.strip())
    if not tokens:
        raise ValueError(
            "--profiles needs all, none, or a comma-separated list of family directory names "
            "(for example anthropic-claude), file stems, or front-matter api_id values"
        )
    return InitProfilesSelection("subset", tokens)


def validate_init_profiles_selection(
    selection: InitProfilesSelection, src_dir: Path
) -> InitProfilesSelection:
    if selection.mode != "subset":
        return selection
    families, names, rels_by_token = index_bundled_profile_names(src_dir)
    unknown = selection.tokens - families - names
    if unknown:
        raise ValueError(f"unknown profile name(s): {', '.join(sorted(unknown))}")
    rels = frozenset(r for t in selection.tokens for r in rels_by_token[t])
    return InitProfilesSelection(selection.mode, selection.tokens, rels)


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
    return rel_in.as_posix() in selection.profile_rels


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
            profile_selection = validate_init_profiles_selection(profile_selection, profiles_src)
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
