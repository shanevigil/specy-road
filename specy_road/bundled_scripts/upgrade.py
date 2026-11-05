#!/usr/bin/env python3
"""Bring a consumer repo up to the installed specy-road: ``specy-road upgrade``.

After ``pip install -U specy-road``, ``pipx upgrade specy-road`` or
``uv tool upgrade specy-road`` the repo still carries what older versions
copied into it. Four commands fix that, and adopters of 0.3.1rc1 ran them from
memory, in different orders, and stopped at different points: one kept
duplicate ``/specyrd-…`` commands because the ``rm`` was buried in output,
another never got the ``AGENTS.md`` block. This runs the same commands, in
order, and nothing else:

1. ``refresh-schemas``  — ``schemas/``
2. ``refresh-profiles`` — missing ``model-profiles/`` files, never overwriting
3. shipped docs         — the ``docs/`` files the ``.specyrd/AGENTS.md`` load order names,
   when missing (never overwriting)
4. ``refresh-stubs``    — IDE skills and the managed blocks (``--prune`` deletes
   the stubs this version no longer installs, and ``.cursor``/``.codex`` copies
   of the skills that are links or verbatim stubs)
5. ``validate``, then ``digest --check``

It first prints the running version, its ``sys.prefix`` and every
``specy-road``/``specyrd`` on PATH. After writing it names each file its own
writes pushed over the project's file-limits cap (a file already over is not
blamed on it), and lists the other git worktrees, which still carry the old
managed files while sharing this install.

Each step keeps its own narrow contract; the roadmap, planning sheets and
anything outside a managed block are never touched. ``--dry-run`` lists what
the refreshes would write, then applies them to a temporary copy of the
project and runs ``validate`` there; the checkout is never written. The exit
code is ``validate``'s: a missing or drifted digest is reported, not failed.
Read validate's notices for what the new version reports (held milestones
among them), then run ``specy-road digest``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from specy_road import __version__
from specy_road.agents_md_block import load_order_paths, print_migration, render_rules
from specy_road.bundled_scripts.digest_cli import cmd_digest
from specy_road.bundled_scripts.refresh_profiles import refresh_profiles, selection_notice
from specy_road.bundled_scripts.refresh_schemas import SCHEMAS_DIRNAME, missing_schema_names, refresh_schemas
from specy_road.bundled_scripts.refresh_stubs import _prefix, _report, _resolve_root, refresh_stubs
from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.digest import DEFAULT_OUTPUT
from specy_road.file_limits_engine import build_overlay_match_sets, collect_tracked_files, line_count, resolve_limits
from specy_road.git_subprocess import git_text
from specy_road.init_project import project_template_root
from specy_road.managed_block import resolves_outside
from specy_road.runtime_paths import add_repo_root_arg, git_root, project_root, source_scan_root
from specy_road.version_skew import print_install_report

CHECKLIST = (
    "Review `git diff` and `git status` (new schema and skill files are untracked), then commit.",
    "Text you wrote outside the managed blocks (CLAUDE.md, docs) may still name the old version"
    " or .cursor/commands/; search for it.",
)


def _section(title: str) -> None:
    print(f"\n== {title}", flush=True)   # the steps warn on stderr; keep a piped log in order


def copy_missing_docs(project: Path, *, dry_run: bool = False) -> list[str]:
    """Copy the ``docs/`` files this version's load order names and the project lacks.

    The load order sends every agent to them, and only ``init project`` copied
    them, so a repo scaffolded before a doc shipped has a load order pointing at
    nothing. An existing file (or link) is the project's and stays as it is.
    """
    src_root = project_template_root()
    copied: list[str] = []
    for rel in load_order_paths(render_rules().splitlines()):
        src, dst = src_root / rel, project / rel
        if not rel.startswith("docs/") or not src.is_file() or dst.exists() or dst.is_symlink():
            continue
        if resolves_outside(project, dst):
            print(f"skipped {rel} (a symlink leads outside the repository)")
            continue
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        copied.append(rel)
    return copied


def _refresh(project: Path, checkout: Path, *, dry_run: bool, prune: bool) -> None:
    verb = "would write" if dry_run else "wrote"
    _section("refresh-schemas")
    new = {f"{SCHEMAS_DIRNAME}/{name}" for name in missing_schema_names(project)}
    schemas = refresh_schemas(project, dry_run=dry_run)
    for rel in schemas:
        print(f"{verb} {rel}" + (" (new in this version)" if rel in new else ""))
    if not schemas:
        print("schemas/ already current")

    _section("refresh-profiles")
    profiles, kept = refresh_profiles(project, dry_run=dry_run)
    for rel in profiles:
        print(f"{verb} {rel}")
    notice = selection_notice(profiles, kept, roster=True)
    if notice:
        print(notice)

    _section("shipped docs")
    docs = copy_missing_docs(project, dry_run=dry_run)
    for rel in docs:
        print(f"{verb} {rel} (named in the .specyrd/AGENTS.md load order)")
    if not docs:
        print("every shipped doc the load order names is present")

    _section("refresh-stubs")
    print_migration(project, _prefix(checkout, project))
    written, orphans = refresh_stubs(checkout, dry_run=dry_run, project=project, prune=prune)
    if written or orphans:
        _report(written, orphans, dry_run=dry_run, pruned=prune, footer=False)
    else:
        print("stubs and managed blocks already current")


def _check(project: Path) -> tuple[bool, bool]:
    """``(validate passed, digest current)``; both print their own detail."""
    _section("validate")
    try:
        validate_at(project)
        valid = True
    except SystemExit as e:
        valid = not e.code
    _section("digest --check")
    ns = argparse.Namespace(output=DEFAULT_OUTPUT, check=True, repo_root=project)
    return valid, cmd_digest(ns) == 0


def _capped_lines(project: Path) -> dict[str, tuple[int, int]]:
    """``{path: (lines, cap)}`` for every file the project's ``constraints/file-limits.yaml`` caps.

    Read the way ``specy-road file-limits`` reads it: globs anchored at the
    source scan root, overlays applied, git-ignored files skipped.
    """
    cfg_path = project / "constraints" / "file-limits.yaml"
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else None
    except (OSError, yaml.YAMLError):
        cfg = None
    if not isinstance(cfg, dict):
        return {}
    root = source_scan_root(project)
    overlays = build_overlay_match_sets(root, cfg)
    out: dict[str, tuple[int, int]] = {}
    for path in collect_tracked_files(root, cfg):
        rel = path.relative_to(root).as_posix()
        out[rel] = (line_count(path), resolve_limits(rel, cfg, overlays).max_lines_per_file)
    return out


def _report_line_caps(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]) -> None:
    """Name each file this run changed that is now over its cap; one already over is not blamed."""
    lines: list[str] = []
    for rel, (new, cap) in sorted(after.items()):
        old = before[rel][0] if rel in before else 0
        if new <= cap or (rel in before and old == new):
            continue
        if old > cap:
            lines.append(f"{rel}: already over its cap before this upgrade ({old} -> {new} lines, cap {cap})")
        else:
            lines.append(f"{rel}: this upgrade pushed it over its cap: {old} -> {new} lines (cap {cap})")
    if lines:
        _section("file-limits on the files it wrote")
        for line in lines:
            print(line)


def _apply(project: Path, checkout: Path, *, prune: bool) -> None:
    """Run the refreshes for real, then check their writes against the line caps."""
    before = _capped_lines(project)
    _refresh(project, checkout, dry_run=False, prune=prune)
    _report_line_caps(before, _capped_lines(project))


def _copy_checkout(checkout: Path, project: Path, dest: Path) -> None:
    """Copy what the refreshes and validate read into ``dest``: git's tracked and
    unignored files plus every ``.specyrd/`` file, without ``.git`` or the project's ``work/``.

    A link into the checkout is re-pointed into the copy, so a write through it
    lands in the copy and never in the checkout.
    """
    work = project / "work"
    listed = git_text(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], checkout)
    rels = {Path(r) for r in (listed or "").split("\0") if r}
    if listed is None:
        rels = {p.relative_to(checkout) for p in checkout.rglob("*") if p.is_file() or p.is_symlink()}
    rels |= {p.relative_to(checkout) for d in {checkout, project} for p in (d / ".specyrd").rglob("*")
             if p.is_file()}
    for rel in rels:
        src, dst = checkout / rel, dest / rel
        if ".git" in rel.parts or src.is_relative_to(work) or not (src.is_file() or src.is_symlink()):
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_symlink():
            target = Path(os.readlink(src))
            if target.is_absolute() and target.is_relative_to(checkout):
                target = dest / target.relative_to(checkout)
            dst.symlink_to(target)
        else:
            shutil.copy2(src, dst)
    # validate reads git (tracked files for touch zones, ignore rules): one commit of the copy.
    for cmd in (["init", "-q"], ["add", "-A"],
                ["-c", "user.name=specy-road", "-c", "user.email=upgrade@specy-road.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", "upgrade preview"]):
        subprocess.run(["git", "-C", str(dest), *cmd], check=False, capture_output=True)


def _dry_run(project: Path, checkout: Path, *, prune: bool) -> int:
    """List what the refreshes would write, then validate a temporary copy with them applied."""
    _refresh(project, checkout, dry_run=True, prune=prune)
    _section("applying the refreshes to a temporary copy, then validating it")
    with tempfile.TemporaryDirectory(prefix="specy-road-upgrade-") as tmp:
        copy = Path(tmp).resolve()
        _copy_checkout(checkout, project, copy)
        copy_project = copy / project.relative_to(checkout)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            before = _capped_lines(copy_project)
            _refresh(copy_project, copy, dry_run=False, prune=prune)
        _report_line_caps(before, _capped_lines(copy_project))
        valid, _digest_ok = _check(copy_project)
    print("\n(dry-run; no files written in the checkout. The exit code is validate's on the copy.)")
    return 0 if valid else 1


def _other_worktrees(checkout: Path) -> list[tuple[str, str]]:
    """``(path, branch)`` of every git worktree but this one (as ``doctor`` parses the porcelain list)."""
    here = (git_root(checkout) or checkout).resolve()
    found: list[tuple[str, str]] = []
    for chunk in (git_text(["worktree", "list", "--porcelain"], checkout) or "").split("\n\n"):
        wt = dict(line.partition(" ")[::2] for line in chunk.splitlines())
        if "worktree" not in wt or "bare" in wt or Path(wt["worktree"]).resolve() == here:
            continue
        branch = wt.get("branch", "").removeprefix("refs/heads/") or f"detached at {wt.get('HEAD', '')[:12]}"
        found.append((wt["worktree"], branch))
    return found


def _print_other_worktrees(checkout: Path) -> None:
    others = _other_worktrees(checkout)
    if not others:
        return
    _section("other worktrees")
    for path, branch in others:
        print(f"{path} ({branch}): not upgraded; it still has the old managed files while sharing this install."
              f" Run there: cd {path} && specy-road upgrade")


def run_upgrade(repo_root: Path | None, *, dry_run: bool = False, prune: bool = False) -> int:
    project = project_root(repo_root)
    checkout = _resolve_root(repo_root)
    if dry_run:
        print(f"previewing what specy-road {__version__} would write: {project}")
    else:
        print(f"specy-road {__version__} upgrade: {project}")
    print_install_report()
    if dry_run:
        return _dry_run(project, checkout, prune=prune)
    _apply(project, checkout, prune=prune)
    valid, digest_ok = _check(project)
    _section("next")
    steps = list(CHECKLIST)
    if not digest_ok:
        steps.insert(1, "Run specy-road digest (and specy-road export if roadmap.md is tracked), then commit"
                        " them. Not specy-road sync: it also fast-forwards the integration branch.")
    if not valid:
        steps.insert(0, "Fix the validate errors above; the refreshes are written either way.")
    for step in steps:
        print(f"- {step}")
    _print_other_worktrees(checkout)
    return 0 if valid else 1


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="specy-road upgrade",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_repo_root_arg(p)
    p.add_argument("--dry-run", action="store_true", help="Show what the refreshes would write and validate a temporary copy with them "
                   "applied; change nothing in the checkout.")
    p.add_argument(
        "--prune",
        action="store_true",
        help="Also delete stubs this version no longer installs (e.g. pre-0.3.0 .cursor/commands/specyrd-*.md) "
        "and .cursor/.codex copies of the skills in .agents/skills.",
    )
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    try:
        code = run_upgrade(args.repo_root, dry_run=args.dry_run, prune=args.prune)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    raise SystemExit(code)


if __name__ == "__main__":
    main()
