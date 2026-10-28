#!/usr/bin/env python3
"""Bring a consumer repo up to the installed specy-road: ``specy-road upgrade``.

After ``pip install -U specy-road`` the repo still carries what older versions
copied into it. Four commands fix that, and adopters of 0.3.1rc1 ran them from
memory, in different orders, and stopped at different points: one kept
duplicate ``/specyrd-…`` commands because the ``rm`` was buried in output,
another never got the ``AGENTS.md`` block. This runs the same commands, in
order, and nothing else:

1. ``refresh-schemas``  — ``schemas/``
2. ``refresh-profiles`` — missing ``model-profiles/`` files, never overwriting
3. ``refresh-stubs``    — IDE skills and the managed blocks (``--prune`` deletes
   the stubs this version no longer installs)
4. ``validate``, then ``digest --check``

Each step keeps its own narrow contract; the roadmap, planning sheets and
anything outside a managed block are never touched. ``--dry-run`` stops after
the three refreshes. The exit code is ``validate``'s: a missing or drifted
digest is reported, not failed, because a new version's digest often differs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road import __version__
from specy_road.bundled_scripts.digest_cli import cmd_digest
from specy_road.bundled_scripts.refresh_profiles import refresh_profiles
from specy_road.bundled_scripts.refresh_schemas import SCHEMAS_DIRNAME, missing_schema_names, refresh_schemas
from specy_road.bundled_scripts.refresh_stubs import _report, _resolve_root, refresh_stubs
from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.digest import DEFAULT_OUTPUT
from specy_road.runtime_paths import add_repo_root_arg, project_root

CHECKLIST = (
    "Review `git diff` and `git status` (new schema and skill files are untracked), then commit.",
    "Text you wrote outside the managed blocks (CLAUDE.md, docs) may still name the old version"
    " or .cursor/commands/; search for it.",
)


def _section(title: str) -> None:
    print(f"\n== {title}", flush=True)   # the steps warn on stderr; keep a piped log in order


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
    profiles, _kept = refresh_profiles(project, dry_run=dry_run)
    for rel in profiles:
        print(f"{verb} {rel}")
    if not profiles:
        print("model-profiles/ already has every profile this version ships")

    _section("refresh-stubs")
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


def run_upgrade(repo_root: Path | None, *, dry_run: bool = False, prune: bool = False) -> int:
    project = project_root(repo_root)
    print(f"specy-road {__version__} upgrade: {project}")
    _refresh(project, _resolve_root(repo_root), dry_run=dry_run, prune=prune)
    if dry_run:
        print("\n(dry-run; no files written. Rerun without --dry-run, then it validates.)")
        return 0
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
    return 0 if valid else 1


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="specy-road upgrade",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_repo_root_arg(p)
    p.add_argument("--dry-run", action="store_true", help="Show what the refreshes would write; change nothing.")
    p.add_argument(
        "--prune",
        action="store_true",
        help="Also delete stubs this version no longer installs (e.g. pre-0.3.0 .cursor/commands/specyrd-*.md).",
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
