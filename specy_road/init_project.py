"""Scaffold specy-road kit directories into a target repository root."""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from specy_road import __version__
from specy_road.agent_ignores import apply_and_report
from specy_road.agents_md_block import apply_agents_files
from specy_road.generated_files import GENERATED_COMMITTED, refused_generated_files, regenerate_generated_files
from specy_road.harness_instruction_files import AGENTS_MD
from specy_road.managed_block import CREATED, UNCHANGED, UPDATED
from specy_road.model_profiles import PROFILES_REL, load_profile
from specy_road.runtime_paths import (
    git_root,
    prefix_within,
    project_root,
    specy_road_package_dir,
)


_GITIGNORE = Path(".gitignore")
_MANIFEST = Path(".specyrd") / "manifest.json"
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


def _record_layout(top: Path, prefix: str, written: list[str], *, dry_run: bool) -> None:
    """Note in ``.specyrd/manifest.json`` where the project tree was put.

    ``init project sr`` has always scaffolded into a subfolder, but nothing
    remembered that it had, so every later command had to re-guess. Recording
    it is what makes the nested layout deterministic instead of discovered —
    a repository can hold two roadmaps, and a scan picks one of them silently.

    Appends ``.specyrd/manifest.json (<outcome>)`` to ``written`` when the file
    would change, comparing the bytes ``_save_manifest`` writes, so a dry run
    names it exactly when the real run would write it.
    """
    from specy_road.specyrd_init import _load_manifest, _save_manifest

    manifest = _load_manifest(top)
    manifest["project_root"] = prefix.rstrip("/") or "."
    manifest["specyrd_version"] = __version__
    path = top / _MANIFEST
    old = path.read_text(encoding="utf-8") if path.is_file() else None
    if old == json.dumps(manifest, indent=2) + "\n":
        return
    if not dry_run:
        _save_manifest(top, manifest)
    written.append(f"{_MANIFEST.as_posix()} ({CREATED if old is None else UPDATED})")


def _apply_agents_md(dst: Path, prefix: str, written: list[str], *, dry_run: bool) -> None:
    """AGENTS.md gets a managed stub, not a template file: an existing file gets
    the section inserted, with or without --force. The rules it points at and
    the team addendum go under ``.specyrd/`` (see ``agents_md_block``).

    A missing file gets its H1 before the block is applied, which makes the
    block itself report ``updated``; it is reported as created, as the dry run
    reports it.
    """
    new = not (dst / AGENTS_MD).exists()
    for rel, outcome in apply_agents_files(dst, dry_run=dry_run).items():
        if rel == AGENTS_MD and new and outcome == UPDATED:
            outcome = CREATED
        if outcome != UNCHANGED:
            written.append(f"{prefix}{rel} ({outcome})")


def _copy_templates(
    src: Path,
    dst: Path,
    prefix: str,
    selection: InitProfilesSelection,
    *,
    dry_run: bool,
    force: bool,
) -> tuple[list[str], list[str]]:
    """Copy each template file; return ``(written, skipped)`` as git-root-relative paths."""
    written: list[str] = []
    skipped: list[str] = []
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        # .gitignore is written as the git root's managed block (seeded from
        # this template when missing), never copied: see run_init_project.
        if path.is_dir() or rel == _GITIGNORE or not include_template_profiles_file(rel, selection):
            continue
        out = dst / rel
        if out.exists() and not force:
            skipped.append(f"{prefix}{rel.as_posix()}")
            continue
        if not dry_run:
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, out)
        written.append(f"{prefix}{rel.as_posix()}")
    return written, skipped


def _write_generated(
    dst: Path, prefix: str, written: list[str], skipped: list[str], *, dry_run: bool, force: bool,
) -> None:
    """Render ``roadmap.md`` and ``roadmap-context.md`` from the scaffold graph, so ``export --check``
    and ``digest --check`` pass on a new project. Rendering writes both, so a file already there
    without ``--force`` (a hand-written ``roadmap.md``) skips both, as a template file is skipped.
    """
    present = [name for name in GENERATED_COMMITTED if os.path.lexists(dst / name)]   # a dangling link counts
    if present and not force:
        skipped.extend(f"{prefix}{name}" for name in present)
        return
    refused = refused_generated_files(dst)   # a link out of the project is never written through
    if not dry_run:
        regenerate_generated_files(dst)
    written.extend(f"{prefix}{name}" for name in GENERATED_COMMITTED if name not in refused)
    skipped.extend(f"{prefix}{name} ({why})" for name, why in refused.items())


def _profile_selection(profiles: str) -> InitProfilesSelection:
    """Parse and check ``--profiles``; raises ``ValueError`` naming what is wrong."""
    selection = parse_init_profiles_spec(profiles)
    profiles_src = bundled_profiles_template_dir()
    if profiles_src.is_dir():
        selection = validate_init_profiles_selection(selection, profiles_src)
    return selection


def run_init_project(
    target: Path | None,
    *,
    dry_run: bool = False,
    force: bool = False,
    profiles: str = "all",
) -> int:
    """Copy bundled templates/project into target. Return exit code.

    Every path the run creates or changes is reported once, with the same
    text under ``--dry-run`` as for real: the template files, ``AGENTS.md``,
    both ignore files' managed blocks, ``.specyrd/manifest.json`` and the two
    generated files. Paths are relative to the git root (``sr/roadmap/...`` in
    the nested layout).
    """
    dst = project_root(target) if target else project_root()
    src = project_template_root()
    if not src.is_dir():
        print(f"error: missing project template at {src}", file=sys.stderr)
        return 2
    try:
        selection = _profile_selection(profiles)
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

    # The ignore files live at the git root (dst itself outside a repository)
    # and name project paths with the prefix, so a nested project gets no
    # .gitignore of its own. The template's commented header seeds a missing
    # one only when the two roots coincide: its comments name unprefixed paths.
    top = git_root(next(p for p in (dst, *dst.parents) if p.is_dir()))   # dst may not exist yet
    root = top or dst
    prefix = prefix_within(top, dst) if top else ""
    written, skipped = _copy_templates(src, dst, prefix, selection, dry_run=dry_run, force=force)
    _apply_agents_md(dst, prefix, written, dry_run=dry_run)
    seed = "" if prefix else (src / _GITIGNORE).read_text(encoding="utf-8")
    apply_and_report(root, prefix, written, dry_run=dry_run, gitignore_seed=seed)
    if top is not None:
        _record_layout(top, prefix, written, dry_run=dry_run)
    _write_generated(dst, prefix, written, skipped, dry_run=dry_run, force=force)

    verb = "would write" if dry_run else "wrote"
    for entry in written:
        print(f"{verb} {entry}")
    for entry in skipped:
        print(f"skipped (exists): {entry}")
    if dry_run:
        print(f"dry-run: {len(written)} path(s) would be written or changed under {root}")
        if skipped:
            print(f"dry-run: would skip {len(skipped)} existing (no --force)")
        return 0
    print(f"Initialized specy-road layout under {dst}")
    if prefix:
        print(f"Recorded project_root={prefix.rstrip('/')} in .specyrd/manifest.json")
    return 0
