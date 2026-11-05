"""``specy-road worktree cleanup <ID>`` and ``worktree sweep``: retire landed worktrees, saving hand-off files first.

A reviewer may write its review history into the leaf worktree's own (ignored) ``work/reviews/<ID>/``,
and ``git worktree remove --force`` would delete it. So both commands move those files into the
main checkout's shared hand-off directory before removing anything (:func:`specy_road.review_files.reviews_root`), never
overwriting a different file: a same-named file with other bytes is kept beside it as
``<name>.from-worktree<n>``.

The removal checks are :func:`specy_road.worktree_prune.plan_worktree`'s (branch and ``HEAD`` merged into
the remote's integration tip, nothing uncommitted, untracked, stashed, no running worker, no other
repository inside), plus one: every ignored file removal would delete must be regenerable
(:data:`REGENERABLE`) or a hand-off file just saved. Sweep looks only at worktrees whose branch, or
detached ``HEAD``, the integration branch contains, and keeps any that M14.2's live rules
(:func:`specy_road.doctor_worktrees.live_holders`) hold: a registry claim, a non-terminal worker or a
live session. Removing a worktree ends the session records tied to it or its branch. Remote branches are
never deleted; a local branch only with ``--delete-local-branch``, and only once the integration branch
contains it.

Plan first, act second: :func:`plan_cleanup` reads the untouched tree once (the prune checks, the hand-off
files to save, the workers to end, every refusal) and :func:`execute` acts only on a plan with no refusal.
A directory holding a repository (a ``.git`` file, directory or link, or a bare layout) is never moved:
the hand-off walk stops there and refuses, and the prune walk names its repository.
"""

from __future__ import annotations

import filecmp
import os
import shutil
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path
from types import SimpleNamespace

from specy_road.bundled_scripts.doctor import _complete_leaves
from specy_road.bundled_scripts.grind_session_cleanup import delete_local_branch, merged_into
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.doctor_worktrees import TEMP_WORKTREES, _live, _worktrees, live_holders
from specy_road.git_subprocess import git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.review_files import REVIEWS_REL, reviews_root
from specy_road.runtime_paths import project_prefix
from specy_road.session_presence import end_sessions_for
from specy_road.worker_ops_lifecycle import terminate
from specy_road.worker_orphans import HELD_STATES, terminate_orphaned
from specy_road.worker_state import WorkerRecord, list_records
from specy_road.worktree_prune import PrunePlan, leaf_worktree, plan_worktree, remove

#: Ignored files removal may delete: a directory pattern (``/`` at the end) anywhere in the path, a
#: ``work/`` pattern at the project root.
REGENERABLE = ("__pycache__/", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/", "node_modules/", ".specyrd/cache/",
               "work/prompt-*.md", "work/brief-*.md", "work/.on-complete-*.yaml")


def regenerable(path: str, prefix: str) -> bool:
    """Whether the git-root-relative ignored ``path`` matches :data:`REGENERABLE` (``prefix``: the project's)."""
    rel = path[len(prefix):] if path.startswith(prefix) else None
    for pat in REGENERABLE:
        if pat.endswith("/") and f"/{pat}" in f"/{path}":
            return True
        if rel is not None and rel.count("/") == pat.count("/") and fnmatchcase(rel, pat):
            return True
    return False


@dataclass
class CleanupPlan:
    """Everything one removal does, read from the untouched worktree: nothing is moved or deleted while it is built.

    ``salvage``: ``(file in the worktree, its place under reviews_root(main))``; never a ``.git`` entry or a file
    in a directory that holds one. ``refusals``: every reason not to act; :func:`execute` acts only without any.
    """
    prune: PrunePlan
    salvage: list[tuple[Path, Path]] = field(default_factory=list)
    workers: list[WorkerRecord] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)


def _holds_repo(dirs: list[str], files: list[str]) -> bool:
    """A ``.git`` entry (file, directory or link), or a bare repository's layout: another repository starts here."""
    return ".git" in dirs or ".git" in files or ("HEAD" in files and {"objects", "refs"} <= set(dirs))


def _salvage_list(main: Path, wt: Path, sub: str) -> tuple[list[tuple[Path, Path]], list[str]]:
    """``(moves, refusals)`` for ``wt``'s own ``work/reviews/<sub>``: links are never followed, and a directory
    holding a repository is left in place, unwalked, with a refusal naming it."""
    src_root = wt / project_prefix(main) / REVIEWS_REL
    src, dest_root = (src_root / sub if sub else src_root), reviews_root(main)
    if not src.is_dir() and not src.is_symlink():
        return [], []
    if src.resolve() != wt.resolve() / src.relative_to(wt):
        return [], [f"{src.relative_to(wt).as_posix()} is or lies under a link; hand-off files there are not followed"]
    if src_root.resolve() == dest_root.resolve():
        return [], []
    moves, refusals = [], []
    for top, dirs, files in os.walk(src):   # links are not followed
        d = Path(top)
        if _holds_repo(dirs, files):
            refusals.append(f"{d.relative_to(wt).as_posix()}/ holds a repository; its files are not hand-off files "
                            "and are left in place")
            dirs.clear()
            continue
        moves += [(d / f, dest_root / (d / f).relative_to(src_root)) for f in sorted(files)
                  if not (d / f).is_symlink()]
    return moves, refusals


def _move_one(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    target, n = dest, 0
    while target.exists() and not (target.is_file() and filecmp.cmp(src, target, shallow=False)):
        n += 1
        target = dest.with_name(f"{dest.name}.from-worktree{n}")
    if target.exists():   # the same bytes are already saved there
        src.unlink()
    else:
        shutil.move(src, target)


def _workers_in(main: Path, wt: Path) -> list[WorkerRecord]:
    here = wt.resolve()
    return [r for r in list_records(main, active_only=True) if Path(r.worktree).resolve().is_relative_to(here)]


def plan_cleanup(main: Path, wt: Path, branch: str, sub: str = "") -> CleanupPlan:
    """The whole removal of ``wt``, hand-off files under ``work/reviews/<sub>`` saved first, and every refusal.

    The prune checks (M14.3's foreign-repository walk included) see the tree as it is, hand-off files still
    in place; each ignored file must then be saved by this plan or :func:`regenerable`.
    """
    prune = plan_worktree(main, wt, branch)
    moves, held = _salvage_list(main, wt, sub)
    saved = {f.relative_to(wt).as_posix() for f, _dest in moves}
    prefix = project_prefix(main)
    left = [p for p in prune.ignored if p not in saved and not regenerable(p, prefix)]
    workers = _workers_in(main, wt)
    refusals = prune.refusals + held
    refusals += [f"ignored files that are not regenerable: {', '.join(left)}"] if left else []
    refusals += [f"worker {r.worker_id} is {r.state} in it" for r in workers
                 if r.state not in HELD_STATES and r.state != "running"]   # running: plan_worktree says so
    refusals += [f"worker {r.worker_id} is handed off to a human; `specy-road worker reclaim {r.worker_id}` first"
                 for r in workers if r.state in HELD_STATES and r.lease.get("holder") == "human"]
    return CleanupPlan(prune, moves, workers, refusals)


def execute(plan: CleanupPlan) -> tuple[bool, list[str]]:
    """Carry ``plan`` out: save the hand-off files, end its workers, remove the worktree, end its session records.

    ``(False, refusals)`` without doing anything when it has any.
    """
    if plan.refusals:
        return False, plan.refusals
    main, wt = plan.prune.main, plan.prune.worktree
    for src, dest in plan.salvage:
        _move_one(src, dest)
    lines = [f"saved hand-off file {src.relative_to(wt).as_posix()} to {reviews_root(main)}" for src, _d in plan.salvage]
    lines += [f"terminated worker {terminate(main, r.worker_id).worker_id}" for r in plan.workers]
    failure = remove(plan.prune)
    if failure:
        return False, [failure]
    lines += [f"ended session record {s.agent}" for s in end_sessions_for(main, wt, plan.prune.branch or None)]
    return True, [*lines, f"removed worktree {wt}"]


def cleanup_after_land(root: Path, node_id: str) -> tuple[bool, list[str]]:
    """``worktree cleanup <ID>``: ``(removed, lines)``; refused, nothing is moved or removed and each line is one
    reason. :class:`specy_road.worktree_prune.PruneError` when the leaf has no worktree."""
    main, wt, branch = leaf_worktree(root, node_id)
    return execute(plan_cleanup(main, wt, branch, node_id))


def sweep_decision(ctx: SimpleNamespace, wt: dict[str, str]) -> tuple[str | None, CleanupPlan | None]:
    """Sweep's one keep/remove decision for ``wt``, on git facts: ``(why it is kept, None)`` or ``(None, plan)``.

    In order: not removable at all (locked, this command's own worktree, directory missing, a running check's
    temporary worktree); held by M14.2's live rules (a registry claim, a non-terminal worker, a live session);
    its tip (the branch's, or a detached ``HEAD``) not an ancestor of the integration branch
    (``git merge-base --is-ancestor``; a same-patch or squashed branch is not, and is kept); then every
    :func:`plan_cleanup` refusal (unmerged on the remote, dirty, stashed, foreign repository, unsaved ignored
    files). A branch with no commits of its own that the integration branch contains is landed: once nothing
    holds it, it goes.
    """
    path = Path(wt["worktree"])
    if "locked" in wt:
        return "locked", None
    if path.resolve() == ctx.here:
        return "the worktree this command runs in", None
    if "prunable" in wt or not path.is_dir():
        return "directory missing (`git worktree prune` drops its record)", None
    if path.parent.name.startswith(TEMP_WORKTREES):
        return "a temporary worktree a running specy-road check may be using", None
    branch = wt.get("branch", "").removeprefix("refs/heads/")
    source, why = _live(ctx, wt, branch)
    if source != "none":
        return why, None
    tip = f"refs/heads/{branch}" if branch else wt.get("HEAD", "")
    if not tip or not merged_into(ctx.root, tip, ctx.target):
        what = f"branch {branch}" if branch else f"detached HEAD {tip[:12]}"
        return f"{what} is not an ancestor of {ctx.target}", None
    plan = plan_cleanup(ctx.root, path, branch)
    return ("; ".join(plan.refusals), None) if plan.refusals else (None, plan)


def _sweep_one(ctx: SimpleNamespace, wt: dict[str, str], dry_run: bool, delete_branch: bool) -> str:
    path = Path(wt["worktree"])
    why, plan = sweep_decision(ctx, wt)
    if plan is None:
        return f"kept {path}: {why}"
    branch = plan.prune.branch
    if dry_run:
        return f"would remove {path}" + (f"; would delete branch {branch}" if delete_branch and branch else "")
    removed, lines = execute(plan)
    if not removed:
        return f"kept {path}: {'; '.join(lines)}"
    line = f"removed {path}"
    if delete_branch and branch:
        failed = delete_local_branch(ctx.root, branch, ctx.target)
        line += f"; deleted branch {branch}" if failed is None else f"; kept branch {branch}: {failed['message']}"
    return line


def sweep(root: Path, *, dry_run: bool, delete_branch: bool = False) -> list[str]:
    """``worktree sweep``: one line per linked worktree, ``removed``, ``would remove`` or ``kept: <reason>``.

    Ends orphaned workers first (unless ``dry_run``), so a finished leaf's idle worker does not keep its worktree.
    """
    main = reviews_root(root).parent.parent
    base, remote, _warnings = resolve_integration_defaults(main, explicit_base=None, explicit_remote=None)
    tracking = git_text(["rev-parse", "--verify", "--quiet", f"refs/remotes/{remote}/{base}"], main)
    target = f"{remote}/{base}" if tracking else base
    if not dry_run:
        terminate_orphaned(main)
    nodes = load_roadmap_nodes_at_ref(main, target) or load_roadmap(main)["nodes"]
    held, held_paths = live_holders(main, target, nodes, _complete_leaves(nodes))
    here = Path(git_text(["rev-parse", "--show-toplevel"], root) or root).resolve()
    ctx = SimpleNamespace(root=main, target=target, here=here, held=held, held_paths=held_paths)
    return [_sweep_one(ctx, wt, dry_run, delete_branch) for wt in _worktrees(main)[1:]]
