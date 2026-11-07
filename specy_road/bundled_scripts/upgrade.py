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
3. shipped docs and templates — missing ``docs/`` files the ``.specyrd/AGENTS.md`` load order names
   and missing ``work/*.template.md`` files prompts reference (never overwriting)
4. ``refresh-stubs``    — IDE skills and the managed blocks (``--prune`` deletes
   the stubs this version no longer installs, and ``.cursor``/``.codex`` copies
   of the skills that are links or verbatim stubs)
5. ``validate``, then ``digest --check``; in between, when validate passes, it
   writes ``roadmap-context.md`` (``specy-road digest``) when missing or drifted
   and ``roadmap.md`` (``specy-road export``) when tracked and drifted

It first prints the running version, its ``sys.prefix`` and every
``specy-road``/``specyrd`` on PATH. After writing it names each file its own
writes pushed over the project's file-limits cap (a file already over is not
blamed on it), and lists the other git worktrees, which still carry the old
managed files while sharing this install.

Each step keeps its own narrow contract; the roadmap, planning sheets and
anything outside a managed block are never touched. The refreshes run once, on
a temporary mirror of the checkout that keeps its links; what they wrote there
is the plan, which is then written into the checkout. ``--dry-run`` lists the
same plan, writes it into a temporary copy instead and runs ``validate`` there;
the checkout is never written, and the generated files it would write are
listed as ``would write``. Every git call runs with every ``GIT_`` variable of
the caller's removed and a timeout; in the plan's mirror and the dry run's
copy, git also reads no global or system config and runs no hook, and in the
checkout the caller's own config files apply. The exit code is 2 when a git
call it depends on fails or times out, 1 when ``validate`` fails or a write
is refused, and 0 otherwise. A generated file with a symlink on its path is
refused, and ``digest`` stays a next step, as it does when ``validate`` fails
(nothing is regenerated from an invalid graph). A refused stub, skill file,
skill link or ignore file is printed ``error:``; that path is left as it is,
the rest of the plan is applied. A refused ``AGENTS.md``, ``CLAUDE.md``,
shipped doc, work template or profile stays a report line. Read validate's
notices for what the new version reports (held milestones among them).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shlex
import sys
import tempfile
from pathlib import Path

import yaml

from specy_road import __version__, git_subprocess
from specy_road.agents_md_block import load_order_paths, print_migration, render_rules
from specy_road.bundled_scripts.digest_cli import cmd_digest
from specy_road.bundled_scripts.refresh_profiles import refresh_profiles, selection_notice
from specy_road.bundled_scripts.refresh_schemas import SCHEMAS_DIRNAME, missing_schema_names, refresh_schemas
from specy_road.bundled_scripts.refresh_stubs import _prefix, _report, _resolve_root, refresh_stubs
from specy_road.bundled_scripts.upgrade_generated import GitFailed, checked, regenerate, scratch_environ
from specy_road.bundled_scripts.upgrade_plan import Mirror, Plan, apply_plan, conflicts, make_plan
from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.digest import DEFAULT_OUTPUT
from specy_road.file_limits_engine import build_overlay_match_sets, collect_tracked_files, line_count, resolve_limits
from specy_road.git_subprocess import git_text
from specy_road.ignore_report import attempt, observe, observed, print_matches, scratch_git_env
from specy_road.init_project import project_template_root
from specy_road import safe_write
from specy_road.managed_block import refused_link, rule_refusal
from specy_road.safe_write import SafeWriteError
from specy_road.runtime_paths import add_repo_root_arg, git_root, project_root, source_scan_root
from specy_road.upgrade_templates import (
    copy_missing_work_templates,
    work_template_ship_plan,
    work_template_skip_message,
)
from specy_road.version_skew import print_install_report

CHECKLIST = (
    "Review `git diff` and `git status` (new schema and skill files are untracked), then commit.",
    "Text you wrote outside the managed blocks (CLAUDE.md, docs) may still name the old version"
    " or .cursor/commands/; search for it.",
)


def _section(title: str) -> None:
    print(f"\n== {title}", flush=True)   # the steps warn on stderr; keep a piped log in order


def copy_missing_docs(project: Path, *, dry_run: bool = False, declined: list[str] | None = None) -> list[str]:
    """Copy the ``docs/`` files this version's load order names and the project lacks.

    The load order sends every agent to them, and only ``init project`` copied
    them, so a repo scaffolded before a doc shipped has a load order pointing at
    nothing. An existing file (or link) is the project's and stays as it is.
    A doc the safe-write rule refuses (a link on its path) is appended to ``declined``.
    """
    src_root = project_template_root()
    copied: list[str] = []
    for rel in load_order_paths(render_rules().splitlines()):
        src, dst = src_root / rel, project / rel
        if not rel.startswith("docs/") or not src.is_file() or dst.exists() or dst.is_symlink():
            continue
        if why := refused_link(project, dst):
            print(f"skipped {rel} ({why})")
            if declined is not None:
                declined.append(rel)
            continue
        if not dry_run:
            safe_write.copy(project, src, dst)
        copied.append(rel)
    return copied


# Outcome words with which the refreshes report a path they leave as it is (managed_block, specyrd_skills).
# A ``refused: <why>`` of the safe-write rule (a stub, skill file, skill link or ignore file) is an ``error``
# instead (rule_refusal): it is printed as ``error:`` and the upgrade exits 1.
_DECLINED = {"refused": "refuse", "skipped": "skip", "failed": "fail"}


def _report_schemas(project: Path, verb: str) -> None:
    _section("refresh-schemas")
    new = {f"{SCHEMAS_DIRNAME}/{name}" for name in missing_schema_names(project)}
    schemas = refresh_schemas(project)
    for rel in schemas:
        print(f"{verb} {rel}" + (" (new in this version)" if rel in new else ""))
    if not schemas:
        print("schemas/ already current")


def _report_profiles(project: Path, verb: str) -> None:
    _section("refresh-profiles")
    profiles, kept = refresh_profiles(project)
    for rel in profiles:
        print(f"{verb} {rel}")
    notice = selection_notice(profiles, kept, roster=True)
    if notice:
        print(notice)


def _report_shipped_docs(project: Path, verb: str, existence_root: Path) -> list[str]:
    _section("shipped docs")
    declined_docs: list[str] = []
    docs = copy_missing_docs(project, declined=declined_docs)
    to_copy, refused = work_template_ship_plan(existence_root)
    for rel in docs:
        print(f"{verb} {rel} (named in the .specyrd/AGENTS.md load order)")
    for rel in to_copy:
        print(f"{verb} {rel} (work template referenced by prompts)")
    for rel in refused:
        print(work_template_skip_message(rel))
    if not docs:
        print("every shipped doc the load order names is present")
    if not to_copy and not refused:
        print("every work template prompts reference is present")
    return declined_docs


def _report_stubs_declined(
    project: Path, checkout: Path, *, preview: bool, prune: bool, declined_docs: list[str],
) -> dict[str, str]:
    _section("refresh-stubs")
    print_migration(project, _prefix(checkout, project))
    written, orphans = refresh_stubs(checkout, project=project, prune=prune)
    if written or orphans:
        _report(written, orphans, dry_run=preview, pruned=prune, footer=False)
    else:
        print("stubs and managed blocks already current")
    prefix = _prefix(checkout, project)
    declined = {f"{prefix}{rel}": "refuse" for rel in declined_docs}
    for entry in written:
        if action := _declined(getattr(entry, "outcome", "")):
            declined[entry.path] = action
    return declined


def _declined(outcome: str) -> str | None:
    """The plan action for an outcome that left its path as it was; a rule refusal is printed as ``error:``."""
    if why := rule_refusal(outcome):
        print(f"error: {why}", file=sys.stderr)
        return "error"
    return next((a for word, a in _DECLINED.items() if outcome.startswith(word)), None)


def _refresh(
    project: Path,
    checkout: Path,
    *,
    preview: bool,
    prune: bool,
    existence_project: Path | None = None,
) -> dict[str, str]:
    """Run the refreshes for real on ``checkout`` (the plan's mirror); ``preview`` changes only the wording.

    Returns ``{checkout-relative path: refuse | error | skip | fail}`` for each path they left as it was.
    """
    verb = "would write" if preview else "wrote"
    _report_schemas(project, verb)
    _report_profiles(project, verb)
    declined_docs = _report_shipped_docs(project, verb, existence_project or project)
    return _report_stubs_declined(project, checkout, preview=preview, prune=prune, declined_docs=declined_docs)


_VALIDATE_FAILED = "Fix the validate errors above; the refreshes are written either way."
_REFUSED_STEP = ("Replace each path refused above (error:, refused) with a regular file: any symlink on its path is"
                 " refused, except .claude/skills -> ../.agents/skills or .agents/skills -> ../.claude/skills."
                 " Then run specy-road upgrade again.")


def _check(
    project: Path, tracked_in: Path, verb: str, refused: bool, caller_env: dict[str, str],
) -> tuple[str | None, bool]:
    """``(what failed, as the first next step, or None; generated files done)``; each step prints its own detail.

    A failed ``validate``, a refused generated file, or ``refused`` (the plan
    has an ``error`` entry: a stub, skill file, skill link or ignore file the
    rule refused) fails the run (exit 1).
    The generated files are done only when validate passed (so they were
    regenerated), nothing was refused, and ``digest --check`` passes; otherwise
    ``specy-road digest`` stays a next step.
    """
    _section("validate")
    try:
        validate_at(project)
        valid = True
    except SystemExit as e:
        valid = not e.code
    generated_refused = False
    if valid:
        _section("generated files")
        generated_refused = regenerate(project, tracked_in, verb, caller_env)
    _section("digest --check")
    ns = argparse.Namespace(output=DEFAULT_OUTPUT, check=True, repo_root=project)
    # A digest the rule refuses is never read (regenerate printed its refusal): not current.
    current = not refused_link(project, project / DEFAULT_OUTPUT) and cmd_digest(ns) == 0
    failed = (_VALIDATE_FAILED if not valid else _REFUSED_STEP if refused or generated_refused else None)
    return failed, valid and current and not generated_refused


_DIGEST_STEP = ("Run specy-road digest (and specy-road export if roadmap.md is tracked), then commit"
                " them. Not specy-road sync: it also fast-forwards the integration branch.")


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


def _plan(project: Path, checkout: Path, *, preview: bool, prune: bool, defer_ignore: bool = False):
    real = project.resolve()

    def refresh(sandbox_project: Path, sandbox_checkout: Path) -> dict[str, str]:
        return _refresh(
            sandbox_project,
            sandbox_checkout,
            preview=preview,
            prune=prune,
            existence_project=real,
        )

    return make_plan(checkout, project, refresh, defer_ignore=defer_ignore)


def _writes_gitignore(plan: Plan) -> bool:
    """Whether the plan replaces the checkout's top-level ``.gitignore``."""
    return any(e.action == "write" and e.path == ".gitignore" for e in plan.entries)


@contextlib.contextmanager
def _checkout_ignore_note(checkout: Path, plan: Plan):
    """Print the ignore note from the checkout, observed just before the ``.gitignore`` write and read just after."""
    before = attempt(lambda: observe(checkout)) if _writes_gitignore(plan) else None
    try:
        yield
    finally:
        if before is not None:
            found = before if isinstance(before, str) else attempt(lambda: observed(checkout, before))
            print_matches(found, estimated=False)


def _apply(project: Path, checkout: Path, *, prune: bool) -> bool:
    """Make the plan, write it into the checkout, then check its writes against the line caps.

    Returns whether the plan has an ``error`` entry (applied as nothing, the rest applied).
    The plan's mirror has an empty index, so the ignore note is taken here, around the write.
    """
    before = _capped_lines(project)
    plan = _plan(project, checkout, preview=False, prune=prune, defer_ignore=True)
    stale = conflicts(plan)
    if stale:
        raise ValueError(f"{', '.join(stale)} changed while the upgrade ran; nothing was written, run it again")
    with _checkout_ignore_note(checkout, plan):
        apply_plan(plan)
    copy_missing_work_templates(project)
    _report_line_caps(before, _capped_lines(project))
    return any(e.action == "error" for e in plan.entries)


def _commit_copy(copy: Mirror) -> None:
    """One commit of the copy, for validate reads git (tracked files for touch zones, ignore rules).

    A file the mirror could not read stays out of it, or ``git add`` would exit
    non-zero on a checkout the real run handles. ``--allow-empty``: a copy git
    ignores whole has nothing to commit, and that is no failure.
    """
    if not (copy.repo / ".git").is_dir():
        raise GitFailed("git init failed in the temporary copy (no .git was created)")
    hooks = ["-c", f"core.hooksPath={copy.hooks}"]
    skipped = [f":(exclude,literal){p.relative_to(copy.repo).as_posix()}"
               for p in copy.unreadable if p.is_relative_to(copy.repo)]
    checked(git_subprocess.run([*hooks, "add", "-A", "--ignore-errors", "--", ".", *skipped], copy.repo), "add")
    checked(git_subprocess.run(
        [*hooks, "-c", "user.name=specy-road", "-c", "user.email=upgrade@specy-road.invalid",
         "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "--allow-empty", "-m", "upgrade preview"],
        copy.repo), "commit")


def _dry_run(project: Path, checkout: Path, *, prune: bool) -> int:
    """Make the same plan, write it into a temporary copy of the checkout, and validate the copy."""
    with tempfile.TemporaryDirectory(prefix="specy-road-upgrade-") as tmp, scratch_environ(Path(tmp)) as caller_env:
        plan = _plan(project, checkout, preview=True, prune=prune)
        _section("applying the refreshes to a temporary copy, then validating it")
        copy = Mirror(checkout, Path(tmp), project / "work").build()
        _commit_copy(copy)
        copy_project = copy.to_sandbox(project.resolve())
        before = _capped_lines(copy_project)
        apply_plan(plan, copy.to_sandbox)
        copy_missing_work_templates(copy_project, existence_root=project)
        _report_line_caps(before, _capped_lines(copy_project))
        failed, _digest_ok = _check(copy_project, project, "would write",
                                    any(e.action == "error" for e in plan.entries), caller_env)
    changed = plan.changed_since()
    if changed:
        print(f"error: dry run modified {', '.join(changed)} in {checkout}; this is a bug in specy-road upgrade,"
              " please report it", file=sys.stderr)
        return 2
    print("\n(dry-run; no files written in the checkout. The exit code is 1 when validate fails on the copy"
          " or a write is refused.)")
    return 0 if failed is None else 1


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
              f" Run there: cd {shlex.quote(path)} && specy-road upgrade")


def run_upgrade(repo_root: Path | None, *, dry_run: bool = False, prune: bool = False) -> int:
    """The upgrade's exit code; a git call it depends on failing prints why and is 2."""
    try:
        with scratch_environ(None):
            return _upgrade(repo_root, dry_run=dry_run, prune=prune)
    except GitFailed as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


def _upgrade(repo_root: Path | None, *, dry_run: bool, prune: bool) -> int:
    project = project_root(repo_root)
    checkout = _resolve_root(repo_root)
    if dry_run:
        print(f"previewing what specy-road {__version__} would write: {project}")
    else:
        print(f"specy-road {__version__} upgrade: {project}")
    print_install_report()
    try:
        if dry_run:
            return _dry_run(project, checkout, prune=prune)
        refused = _apply(project, checkout, prune=prune)
    except SafeWriteError as e:   # refused before the first write: nothing was applied
        print(f"error: {e}", file=sys.stderr)
        return 1
    failed, digest_ok = _check(project, project, "wrote", refused, scratch_git_env())
    _section("next")
    steps = [failed, CHECKLIST[0], None if digest_ok else _DIGEST_STEP, *CHECKLIST[1:]]
    for step in filter(None, steps):
        print(f"- {step}")
    _print_other_worktrees(checkout)
    return 0 if failed is None else 1


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
        with safe_write.exit_on_refusal():   # a refusal, or a symlink loop met before the rule
            code = run_upgrade(args.repo_root, dry_run=args.dry_run, prune=args.prune)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    raise SystemExit(code)


if __name__ == "__main__":
    main()
