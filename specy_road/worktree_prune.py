"""``specy-road worktree prune <ID>``: remove a leaf's worktree only when nothing in it would be lost.

The leaf's worktree is ``work/.worktrees/<codename>`` in the main checkout, on
``feature/rm-<codename>``. It is removed only when the worktree's ``HEAD``,
that branch (local, remote-tracking, and on the remote itself, wherever each
exists) are merged into the remote's actual integration tip, and the worktree has
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
checkout's copy, and any stash refuses. A worker in state ``running`` in the
worktree refuses too: its harness is writing there.

Any other directory in the worktree holding a ``.git`` (a linked worktree, a
checkout or an initialized submodule of another repository, not a configured
nested repo itself) or laid out as a bare repository refuses, naming its
repository, branch and the commits its upstream lacks: removal would delete it,
and this command never prunes another repository's worktree. They are found by
walking the filesystem, links not followed, so clean tracked directories are
seen too; a directory the walk cannot read refuses.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from specy_road.bundled_scripts.grind_session_cleanup import merged_into
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.git_subprocess import DEFAULT_TIMEOUT, git_code, git_stdout, git_text, run
from specy_road.git_workflow_config import load_git_workflow_config, resolve_integration_defaults
from specy_road.nested_repos import _common_dir, is_repo_top, nested_repos
from specy_road.review_files import reviews_root
from specy_road.runtime_paths import project_prefix
from specy_road.worker_state import list_records


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
    foreign: list[Path] = field(default_factory=list)   # other repositories' worktrees or checkouts inside it
    unscanned: list[str] = field(default_factory=list)   # directories the foreign-repository walk could not read


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
    # -z, read as bytes: paths come unquoted and untouched (text mode's universal newlines would turn a
    # '\r' in a name into '\n'), each record ending in NUL; a rename or copy record carries its source
    # path as the next field. --untracked-files=all names each file inside an untracked or ignored
    # directory, so the list says exactly what removal deletes. Foreign repositories are not found from
    # this list (a clean tracked one is not in it): see _walk_foreign.
    try:
        r = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--ignored", "--untracked-files=all"],
                           cwd=d, capture_output=True, timeout=DEFAULT_TIMEOUT, check=False)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if r.returncode:
        return None
    changed, ignored = [], []
    fields = iter(os.fsdecode(f) for f in r.stdout.split(b"\0"))
    for rec in fields:
        if not rec:
            continue
        paths = [rec[3:], next(fields, "")] if rec[0] in "RC" or rec[1] in "RC" else [rec[3:]]
        for path in filter(None, paths):
            if skip and f"{path.rstrip('/')}/".startswith(skip):
                continue
            (ignored if rec.startswith("!! ") else changed).append(path)
    return changed, ignored


_STASH_ON = re.compile(r"^(?:WIP on|On) ([^:]+):")   # git's own subjects; a branch name cannot hold ':'


def _stashes(d: Path, branch: str, linked: bool) -> list[str] | None:
    """Stash subjects that refuse: any for a clone; for a linked worktree (stash is shared), every one whose
    subject does not name another branch: made on ``branch``, on a detached ``HEAD`` (an uncovered nested
    repo is detached) or under a custom subject could be this worktree's. ``None`` when the stash list
    cannot be read, which refuses too: no stash cannot be told from an unreadable one."""
    def names_another_branch(subject: str) -> bool:
        m = _STASH_ON.match(subject)
        return bool(m) and m.group(1) not in (branch, "(no branch)")

    out = git_stdout(["stash", "list", "--format=%gs"], d)
    if out is None:
        return None
    return [s for s in out.splitlines() if not (linked and names_another_branch(s))]


def _held(repo: Path, sha: str, refs: list[str]) -> bool:
    return bool(git_text(["for-each-ref", "--count=1", "--contains", sha, *refs], repo))


def _lost_tips(src: Path, d: Path, linked: bool) -> list[str] | None:
    """``HEAD`` and, for a clone, each local branch and remote-tracking ref whose tip no branch or
    remote-tracking ref of ``src`` holds.

    A clone's own remote-tracking refs go with its directory and may be stale (the remote's branch
    deleted since), so they are tips to keep, never a place that keeps them. ``None`` when a clone's refs
    cannot be listed.
    """
    tips = [("HEAD", git_text(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"], d))]
    if not linked:
        out = git_text(["for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads", "refs/remotes"], d)
        if out is None:
            return None
        tips += [tuple(line.rsplit(" ", 1)) for line in out.splitlines()]
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
        stashes, lost = _stashes(d, plan.branch, linked), _lost_tips(src, d, linked)
        if stashes is None:
            plan.refusals.append(f"{label}: cannot read the stash list")
        elif stashes:
            plan.refusals.append(f"{label}: stashes: {'; '.join(stashes)}")
        if lost is None:
            plan.refusals.append(f"{label}: cannot list its branches and remote-tracking refs")
        elif lost:
            plan.refusals.append(f"{label}: commits on no branch or remote-tracking ref of {src}: "
                                 f"{', '.join(lost)}")


_SHOWN = 20   # commits listed per foreign repository; a checkout with no remote could list its whole history


def _walk_foreign(wt: Path, exempt: set[Path]) -> tuple[list[Path], list[str]]:
    """``(foreign, unreadable)``: every directory below ``wt``, but not in ``exempt``, holding a ``.git``
    entry (file, directory or link) or laid out as a bare repository; and each directory that could not
    be read, which refuses too, since what is in it is unknown.

    Walks the filesystem itself, not git's view of it: a clean tracked directory, or a submodule at its
    recorded commit, is in no status output. Links are never followed (removal deletes the link, not
    its target). A found repository is not descended into: it refuses already.
    """
    found, unreadable = [], []

    def unread(e: OSError) -> None:
        unreadable.append(f"cannot read {e.filename}: {e.strerror}; removal would delete what it holds unchecked")

    for top, dirs, files in os.walk(wt, onerror=unread):
        d = Path(top)
        bare = "HEAD" in files and {"objects", "refs"} <= set(dirs)
        if d != wt and d not in exempt and (".git" in dirs or ".git" in files or bare):
            found.append(d)
            dirs.clear()
        elif ".git" in dirs:
            dirs.remove(".git")   # this worktree's or an exempt repository's own git directory
    return sorted(found), unreadable


def _foreign_refusal(wt: Path, d: Path) -> str:
    """Why ``d``, another repository's linked worktree, checkout (a ``.git`` directory, or a ``.git`` file
    naming its own git directory, as a submodule's does) or bare repository, refuses."""
    common = _common_dir(d)
    git_dir = git_text(["rev-parse", "--absolute-git-dir"], d)
    linked = bool(common and git_dir) and Path(git_dir).resolve() != common
    bare = not (d / ".git").exists() and not os.path.islink(d / ".git")
    if linked:
        repo = common.parent if common.name == ".git" else common
    else:
        repo = d if bare or (d / ".git").is_dir() else (common or d)
    branch = git_text(["rev-parse", "--abbrev-ref", "HEAD"], d) or "unknown"
    upstream = git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], d)
    span = ["@{u}..HEAD"] if upstream else ["HEAD", "--not", "--remotes"]
    log = git_text(["log", "--oneline", f"--max-count={_SHOWN + 1}", *span], d)
    lacks = f"its upstream {upstream}" if upstream else "every remote-tracking ref"
    if log is None:
        commits = f"commits {lacks} lacks cannot be listed"
    else:
        lines = log.splitlines()
        more = " (and more)" if len(lines) > _SHOWN else ""
        commits = f"commits {lacks} lacks: {'; '.join(lines[:_SHOWN])}{more}" if lines else f"no commits {lacks} lacks"
    kind, step = (("linked worktree", f"`git -C {repo} worktree remove {d}`") if linked
                  else ("bare clone" if bare else "checkout", "move it out of the worktree"))
    return (f"{d.relative_to(wt).as_posix()}/ is a {kind} of another repository, {repo or 'unknown'}, on {branch}; "
            f"{commits}; removal would delete it: land or push those commits, then {step}")


def _remote_heads(main: Path, remote: str, branches: list[str]) -> tuple[dict[str, str], str | None]:
    """``({branch: sha}, None)``: the remote's actual tips of those of ``branches`` it has, with their commits here.

    Read with ``ls-remote``, so neither stale remote-tracking refs nor a fetch refspec that leaves a
    branch out can hide a peer's push; the commits are then fetched by branch name. ``({}, why)`` when
    the remote, or any of those commits, cannot be read.
    """
    want = {f"refs/heads/{b}": b for b in branches}
    r = run(["ls-remote", remote, *want], main)
    if not r.ok:
        return {}, f"cannot read {remote} (git ls-remote {remote}: {r.message})"
    tips = {want[ref]: sha for sha, _, ref in (line.partition("\t") for line in r.out.splitlines()) if ref in want}
    if tips:
        code, out = git_code(["fetch", "--no-tags", "--no-write-fetch-head", remote,
                              *(f"refs/heads/{b}" for b in tips)], main)
        if code:
            return {}, f"cannot fetch {', '.join(tips)} from {remote}: {out}"
    missing = [b for b, sha in tips.items() if git_code(["cat-file", "-e", f"{sha}^{{commit}}"], main)[0]]
    if missing:
        return {}, f"the commits {remote} has at {', '.join(missing)} are not here after fetching them"
    return tips, None


def plan_prune(root: Path, node_id: str) -> PrunePlan:
    """What removing ``node_id``'s worktree would delete, and every reason it must not; :class:`PruneError` if absent."""
    main, wt, branch = leaf_worktree(root, node_id)
    plan, prefix = PrunePlan(main, wt, branch), project_prefix(main)
    plan.refusals += [f"worker {r.worker_id} is running in it; wait for it or `specy-road worker terminate "
                      f"{r.worker_id}`" for r in list_records(main)
                      if r.state == "running" and Path(r.worktree).resolve().is_relative_to(wt.resolve())]
    _cfg, cfg_err = load_git_workflow_config(main)
    if cfg_err:   # nested_repos would read as none, and their clones would go unchecked with the worktree
        plan.refusals.append(f"{cfg_err}; fix it, then re-run: without it the nested repositories cannot be checked")
        return plan
    base, remote, _warns = resolve_integration_defaults(main, explicit_base=None, explicit_remote=None)
    # The remote's own tips, not remote-tracking refs as they last stood: a peer may have pushed to the
    # leaf branch since they were merged, and the fetch refspec may not cover it.
    tips, why = _remote_heads(main, remote, [base, branch])
    if why:
        plan.refusals.append(f"{why}; merged cannot be judged without it")
    elif base not in tips:
        plan.refusals.append(f"{remote} has no {base} to judge merged against")
    else:
        target = f"{remote}'s {base} ({tips[base][:12]})"
        # Every leaf ref that exists, local, remote-tracking and on the remote: any may hold work the
        # others lack, and with none (the branch deleted after landing) the worktree's HEAD alone is checked.
        heads = [("the worktree's HEAD", git_text(["rev-parse", "HEAD"], wt) or "HEAD")]
        heads += [(label, ref) for label, ref in ((branch, f"refs/heads/{branch}"),
                                                  (f"{remote}/{branch}", f"refs/remotes/{remote}/{branch}"))
                  if git_text(["rev-parse", "--verify", "--quiet", ref], main)]
        if branch in tips:
            heads.append((f"{branch} on {remote}", tips[branch]))
        plan.refusals += [f"{label} is not merged into {target}" for label, ref in heads
                          if not merged_into(main, ref, tips[base])]
    _check_nested(plan, main, prefix)
    state = _status(wt, tuple(f"{d.relative_to(wt).as_posix()}/" for _src, d, _linked in plan.nested))
    if state is None:
        plan.refusals.append("cannot read git status of the worktree")
    else:
        changed, ignored = state
        plan.ignored = ignored + plan.ignored
        if changed:
            plan.refusals.append(f"uncommitted or untracked: {', '.join(changed)}")
    # Every configured nested repo is exempt itself, but what it holds is walked like the rest.
    plan.foreign, plan.unscanned = _walk_foreign(wt, {d for _src, d, _linked in plan.nested})
    plan.refusals += [_foreign_refusal(wt, d) for d in plan.foreign] + plan.unscanned
    stashes = _stashes(wt, branch, linked=True)
    if stashes is None:
        plan.refusals.append("cannot read the stash list")
    elif stashes:
        plan.refusals.append(f"stashes that may be this worktree's: {'; '.join(stashes)}")
    return plan


def remove(plan: PrunePlan) -> str | None:
    """Remove the nested repositories, then the worktree; the failure, or ``None``.

    ``--force`` only because the ignored files listed would otherwise stop git:
    :func:`plan_prune` has already refused anything else it would delete. Another repository's worktree or
    checkout inside it refuses here too, so a caller that skips the refusals still deletes nothing.
    """
    if plan.foreign:
        return f"{plan.worktree} holds another repository's worktree or checkout: " + \
            ", ".join(str(d) for d in plan.foreign)
    if plan.unscanned:
        return "; ".join(plan.unscanned)
    for src, d, linked in plan.nested:
        if linked:
            code, out = git_code(["worktree", "remove", "--force", str(d)], src)
            if code:
                return f"git -C {src} worktree remove {d} failed: {out}"
        else:
            try:
                shutil.rmtree(d)
            except OSError as e:
                return f"cannot remove {d}: {e}"
    code, out = git_code(["worktree", "remove", "--force", str(plan.worktree)], plan.main)
    return f"git worktree remove {plan.worktree} failed: {out}" if code else None
