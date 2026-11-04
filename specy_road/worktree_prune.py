"""``specy-road worktree prune <ID>``: remove a leaf's worktree only when nothing in it would be lost.

The leaf's worktree is ``work/.worktrees/<codename>`` in the main checkout, on
``feature/rm-<codename>``. It is removed only when that branch and the
worktree's ``HEAD`` are merged into the integration branch (the remote-tracking
ref as it stands, else the local one; nothing is fetched) and the worktree has
no uncommitted changes, no untracked files git does not ignore, and no stash
that could be its own (see below). Ignored files are deleted
with it, so they are listed first.

Each ``nested_repos`` repository inside the worktree is checked too. A linked
worktree of the main checkout's copy shares its branches and stash, so only a
``HEAD`` no branch or remote-tracking ref holds is at risk. Its stash stack is
shared too, so a stash refuses unless its subject names another branch: one made
on the leaf's branch, on a detached ``HEAD`` (``On (no branch):`` does not say
which worktree made it) or under a custom subject (``git stash store -m``)
cannot be told apart from this worktree's. A full clone loses its branches,
remote-tracking refs and stash with its directory, so each of its branch and
remote-tracking tips must be held by a branch or remote-tracking ref of the main
checkout's copy, and any stash refuses.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from specy_road.bundled_scripts.grind_session_cleanup import merged_into
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.finish_implementation_check import base_ref
from specy_road.git_subprocess import git_code, git_stdout, git_text, local_branch_exists
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.nested_repos import _common_dir, is_repo_top, nested_repos
from specy_road.review_files import reviews_root
from specy_road.runtime_paths import project_prefix


class PruneError(RuntimeError):
    """The leaf or its worktree cannot be found."""


@dataclass
class PrunePlan:
    main: Path   # the main checkout's project root
    worktree: Path
    branch: str
    refusals: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)   # git-root-relative paths removal deletes
    nested: list[tuple[Path, Path, bool]] = field(default_factory=list)   # (main copy, dir, linked worktree)


def leaf_worktree(root: Path, node_id: str) -> tuple[Path, Path, str]:
    """``(main checkout's project root, leaf worktree, leaf branch)`` for ``node_id``, or :class:`PruneError`."""
    node = next((n for n in load_roadmap(root)["nodes"] if n.get("id") == node_id), None)
    if node is None or not node.get("codename"):
        raise PruneError(f"no roadmap node {node_id!r} with a codename")
    main = reviews_root(root).parent.parent
    wt = main / "work" / ".worktrees" / node["codename"]
    if not is_repo_top(wt) or _common_dir(wt) != _common_dir(main):
        raise PruneError(f"{wt} is not a worktree of this repository; nothing to prune")
    return main, wt, f"feature/rm-{node['codename']}"


def _status(d: Path, skip: tuple[str, ...] = ()) -> tuple[list[str], list[str]] | None:
    """``(changed or untracked, ignored)`` paths in ``d``, leaving out those under ``skip``; ``None`` if unreadable."""
    # raw: the status column can start with a space. --untracked-files=all names each file inside an
    # untracked or ignored directory, so the list says exactly what removal deletes.
    out = git_stdout(["status", "--porcelain", "--ignored", "--untracked-files=all"], d)
    if out is None:
        return None
    changed, ignored = [], []
    for line in out.splitlines():
        path = line[3:]
        if skip and f"{path.rstrip('/')}/".startswith(skip):
            continue
        (ignored if line.startswith("!! ") else changed).append(path)
    return changed, ignored


_STASH_ON = re.compile(r"^(?:WIP on|On) ([^:]+):")   # git's own subjects; a branch name cannot hold ':'


def _stashes(d: Path, branch: str, linked: bool) -> list[str]:
    """Stash subjects that refuse: any for a clone; for a linked worktree (stash is shared), every one whose
    subject does not name another branch: made on ``branch``, on a detached ``HEAD`` (an uncovered nested
    repo is detached) or under a custom subject could be this worktree's."""
    def names_another_branch(subject: str) -> bool:
        m = _STASH_ON.match(subject)
        return bool(m) and m.group(1) not in (branch, "(no branch)")

    subjects = (git_text(["stash", "list", "--format=%gs"], d) or "").splitlines()
    return [s for s in subjects if not (linked and names_another_branch(s))]


def _held(repo: Path, sha: str, refs: list[str]) -> bool:
    return bool(git_text(["for-each-ref", "--count=1", "--contains", sha, *refs], repo))


def _lost_tips(src: Path, d: Path, linked: bool) -> list[str]:
    """``HEAD`` and, for a clone, each local branch and remote-tracking ref whose tip no branch or
    remote-tracking ref of ``src`` holds.

    A clone's own remote-tracking refs go with its directory and may be stale (the remote's branch
    deleted since), so they are tips to keep, never a place that keeps them.
    """
    tips = [("HEAD", git_text(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], d))]
    if not linked:
        out = git_text(["for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads", "refs/remotes"], d)
        tips += [tuple(line.rsplit(" ", 1)) for line in (out or "").splitlines()]
    return [f"{name} ({sha[:12]})" for name, sha in tips if sha and not _held(src, sha, ["refs/heads", "refs/remotes"])]


def _check_nested(plan: PrunePlan, main: Path, prefix: str) -> None:
    leaf_root = plan.worktree / prefix
    for nr in nested_repos(main):
        d, src = leaf_root / nr.path, main / nr.path
        if not is_repo_top(d):
            continue
        linked = _common_dir(d) == _common_dir(src)
        plan.nested.append((src, d, linked))
        label = f"nested repo {nr.path} ({'linked worktree' if linked else 'full clone'})"
        state = _status(d)
        if state is None:
            plan.refusals.append(f"{label}: cannot read git status")
            continue
        changed, ignored = state
        plan.ignored += [f"{prefix}{nr.path}/{p}" for p in ignored]
        if changed:
            plan.refusals.append(f"{label}: uncommitted or untracked: {', '.join(changed)}")
        if stashes := _stashes(d, plan.branch, linked):
            plan.refusals.append(f"{label}: stashes: {'; '.join(stashes)}")
        if lost := _lost_tips(src, d, linked):
            plan.refusals.append(f"{label}: commits on no branch or remote-tracking ref of {src}: "
                                 f"{', '.join(lost)}")


def plan_prune(root: Path, node_id: str) -> PrunePlan:
    """What removing ``node_id``'s worktree would delete, and every reason it must not; :class:`PruneError` if absent."""
    main, wt, branch = leaf_worktree(root, node_id)
    plan, prefix = PrunePlan(main, wt, branch), project_prefix(main)
    base, remote, _warns = resolve_integration_defaults(main, explicit_base=None, explicit_remote=None)
    target = base_ref(main, remote, base)
    if target is None:
        plan.refusals.append(f"neither {remote}/{base} nor a local {base} exists")
    else:
        heads = [("the worktree's HEAD", git_text(["rev-parse", "HEAD"], wt) or "HEAD")]
        if local_branch_exists(main, branch):
            heads.append((branch, branch))
        plan.refusals += [f"{label} is not merged into {target}" for label, ref in heads
                          if not merged_into(main, ref, target)]
    _check_nested(plan, main, prefix)
    state = _status(wt, tuple(f"{d.relative_to(wt).as_posix()}/" for _src, d, _linked in plan.nested))
    if state is None:
        plan.refusals.append("cannot read git status of the worktree")
    else:
        changed, ignored = state
        plan.ignored = ignored + plan.ignored
        if changed:
            plan.refusals.append(f"uncommitted or untracked: {', '.join(changed)}")
    if stashes := _stashes(wt, branch, linked=True):
        plan.refusals.append(f"stashes that may be this worktree's: {'; '.join(stashes)}")
    return plan


def remove(plan: PrunePlan) -> str | None:
    """Remove the nested repositories, then the worktree; the failure, or ``None``.

    ``--force`` only because the ignored files listed would otherwise stop git:
    :func:`plan_prune` has already refused anything else it would delete.
    """
    for src, d, linked in plan.nested:
        if linked:
            code, out = git_code(["worktree", "remove", "--force", str(d)], src)
            if code:
                return f"git -C {src} worktree remove {d} failed: {out}"
        else:
            shutil.rmtree(d)
    code, out = git_code(["worktree", "remove", "--force", str(plan.worktree)], plan.main)
    return f"git worktree remove {plan.worktree} failed: {out}" if code else None
