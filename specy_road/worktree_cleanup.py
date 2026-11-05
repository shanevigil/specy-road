"""``specy-road worktree cleanup <ID>`` and ``worktree sweep``: retire landed worktrees, saving hand-off files first.

A reviewer may write its review history into the leaf worktree's own (ignored) ``work/reviews/<ID>/``,
and ``git worktree remove --force`` would delete it. So both commands first move those files into the
main checkout's shared hand-off directory (:func:`specy_road.review_files.reviews_root`), never
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
"""

from __future__ import annotations

import filecmp
import shutil
from fnmatch import fnmatchcase
from pathlib import Path
from types import SimpleNamespace

from specy_road.bundled_scripts.doctor import _complete_leaves
from specy_road.bundled_scripts.grind_session_cleanup import delete_local_branch, merged_into
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.doctor_worktrees import (
    TEMP_WORKTREES,
    _live,
    _worktrees,
    classify,
    containment,
    evidence_kind,
    live_holders,
    merged_how,
)
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


def salvage(main: Path, wt: Path, sub: str = "", *, move: bool = True) -> list[str]:
    """Move the files under ``wt``'s own ``work/reviews/<sub>`` into ``reviews_root(main)/<sub>``.

    Returns their ``wt``-relative paths, what removal no longer loses; with ``move=False`` only lists them.
    """
    src_root = wt / project_prefix(main) / REVIEWS_REL
    src, dest_root = (src_root / sub if sub else src_root), reviews_root(main)
    if not src.is_dir() or src_root.resolve() == dest_root.resolve():
        return []
    saved = []
    for f in sorted(p for p in src.rglob("*") if p.is_file() and not p.is_symlink()):
        saved.append(f.relative_to(wt).as_posix())
        if move:
            _move_one(f, dest_root / f.relative_to(src_root))
    return saved


def _unsaved(plan: PrunePlan, saved: list[str]) -> list[str]:
    prefix = project_prefix(plan.main)
    left = [p for p in plan.ignored if p not in saved and not regenerable(p, prefix)]
    return [f"ignored files that are not regenerable: {', '.join(left)}"] if left else []


def _workers_in(main: Path, wt: Path) -> list[WorkerRecord]:
    here = wt.resolve()
    return [r for r in list_records(main, active_only=True) if Path(r.worktree).resolve().is_relative_to(here)]


def cleanup_after_land(root: Path, node_id: str) -> tuple[bool, list[str]]:
    """``worktree cleanup <ID>``: ``(removed, lines)``; refused, nothing is removed and each line is one reason.

    :class:`specy_road.worktree_prune.PruneError` when the leaf has no worktree.
    """
    main, wt, branch = leaf_worktree(root, node_id)
    saved = salvage(main, wt, node_id)
    plan = plan_worktree(main, wt, branch)
    workers = _workers_in(main, wt)
    refusals = plan.refusals + _unsaved(plan, saved)
    refusals += [f"worker {r.worker_id} is {r.state} in it" for r in workers
                 if r.state not in HELD_STATES and r.state != "running"]   # running: plan_worktree says so
    refusals += [f"worker {r.worker_id} is handed off to a human; `specy-road worker reclaim {r.worker_id}` first"
                 for r in workers if r.state in HELD_STATES and r.lease.get("holder") == "human"]
    if refusals:
        return False, refusals
    lines = [f"saved hand-off file {p} to {reviews_root(main)}" for p in saved]
    lines += [f"terminated worker {terminate(main, r.worker_id).worker_id}" for r in workers]
    failure = remove(plan)
    if failure:
        return False, [failure]
    lines += [f"ended session record {s.agent}" for s in end_sessions_for(main, wt, branch)]
    return True, [*lines, f"removed worktree {wt}"]


def _gate(ctx: SimpleNamespace, wt: dict[str, str]) -> str | None:
    """Why sweep keeps ``wt`` without looking inside it, else ``None``."""
    path = Path(wt["worktree"])
    if "locked" in wt:
        return "locked"
    if path.resolve() == ctx.here:
        return "the worktree this command runs in"
    if "prunable" in wt or not path.is_dir():
        return "directory missing (`git worktree prune` drops its record)"
    if path.parent.name.startswith(TEMP_WORKTREES):
        return "a temporary worktree a running specy-road check may be using"
    branch = wt.get("branch", "").removeprefix("refs/heads/")
    source, why = _live(ctx, wt, branch)
    if source != "none":
        return why
    if branch:
        ref = f"refs/heads/{branch}"
        label, _fix = classify("none", evidence_kind(ctx.root, ref, ctx.target),
                               containment(merged_how(ctx.root, ref, ctx.target)), "local")
        return None if label == "merged" else f"branch {branch}: {label} ({ctx.target})"
    head = wt.get("HEAD", "")
    return None if head and merged_into(ctx.root, head, ctx.target) else \
        f"detached at {head[:12]}, which {ctx.target} does not contain"


def _sweep_one(ctx: SimpleNamespace, wt: dict[str, str], dry_run: bool, delete_branch: bool) -> str:
    path = Path(wt["worktree"])
    why = _gate(ctx, wt)
    if why:
        return f"kept {path}: {why}"
    branch = wt.get("branch", "").removeprefix("refs/heads/")
    saved = salvage(ctx.root, path, move=not dry_run)
    plan = plan_worktree(ctx.root, path, branch)
    reasons = plan.refusals + _unsaved(plan, saved)
    if reasons:
        return f"kept {path}: {'; '.join(reasons)}"
    if dry_run:
        return f"would remove {path}" + (f"; would delete branch {branch}" if delete_branch and branch else "")
    failure = remove(plan)
    if failure:
        return f"kept {path}: {failure}"
    end_sessions_for(ctx.root, path, branch or None)
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
