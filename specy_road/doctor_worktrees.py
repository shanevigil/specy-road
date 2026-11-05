"""``specy-road doctor``'s merged test, live-branch test and worktree findings.

A branch is *live* when an open registry claim (its leaf not Complete), an open milestone rollup
or a worker record that is not terminal holds it: doctor never offers to remove it or its worktree.
A branch is *merged* only when it also has a commit of its own: a fresh claim's tip is an
integration-branch commit, so ancestry alone would call it merged.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable

from specy_road import worker_state
from specy_road.bundled_scripts.grind_session_cleanup import merged_into
from specy_road.git_subprocess import DEFAULT_TIMEOUT, git_checked, git_code, git_text
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.registry_yaml import read_registry, registry_path

# commit-tree needs an identity, and a CI runner may have none configured.
_PROBE_IDENT = ["-c", "user.name=specy-road", "-c", "user.email=doctor@specy-road.invalid"]
SAME_PATCH = "merged (same patch content)"
#: ``mkdtemp`` prefixes of the detached worktrees land check, check-pre-existing, nested land and red/green make.
TEMP_WORKTREES = ("specy-road-land-check-", "specy-road-pre-existing-", "specy-road-nested-land-",
                  "specy-road-red-green-")


@dataclass
class Finding:
    kind: str
    name: str
    reason: str
    remove: Callable[[], str | None] | None   # the failure message, or None; None: --fix leaves it
    done: str


def _all_upstream(root: Path, target: str, ref: str) -> bool:
    lines = (git_text(["cherry", target, ref], root) or "").splitlines()
    return bool(lines) and all(line.startswith("-") for line in lines)


def merged_how(root: Path, ref: str, target: str) -> str | None:
    """``"merged"``, :data:`SAME_PATCH`, or ``None`` when ``target`` lacks ``ref``'s work."""
    if merged_into(root, ref, target):
        return "merged"
    if _all_upstream(root, target, ref):
        return SAME_PATCH
    base = git_text(["merge-base", target, ref], root)
    if base is None:   # an orphan branch shares no history with target
        return None
    # The whole branch as one commit on its merge base: what a squash lands.
    squash = git_checked(
        [*_PROBE_IDENT, "commit-tree", f"{ref}^{{tree}}", "-p", base, "-m", "doctor squash probe"],
        root,
    )
    return SAME_PATCH if _all_upstream(root, target, squash) else None


def has_own_commits(root: Path, ref: str, target: str) -> bool:
    """Whether ``ref`` has a commit made on it, not just the commit it was created at.

    A local branch's reflog decides: an entry after its creation, or a tip that is not the
    creation commit. A remote-tracking ref uses its local branch's reflog when there is one.
    With no reflog, a tip on ``target``'s first-parent line is a commit ``target`` itself had,
    which is where a fresh branch starts.
    """
    branch = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else ref.split("/", 3)[-1]
    local = f"refs/heads/{branch}"
    local_tip = git_text(["rev-parse", "--verify", "--quiet", local], root)
    if local_tip:
        log = (git_text(["reflog", "show", "--format=%H", local], root) or "").split()
        if log:
            return len(log) > 1 or log[-1] != local_tip
    tip = git_text(["rev-parse", ref], root)
    return tip not in (git_text(["rev-list", "--first-parent", target], root) or "").split()


def live_holders(root: Path, target: str, nodes: list[dict[str, Any]], complete: dict[str, str]) -> dict[str, str]:
    """Branch -> ``live: …`` for each branch a worker, an open claim or an open rollup holds."""
    held: dict[str, str] = {}
    for rec in worker_state.list_records(root, active_only=True):
        if rec.branch:
            held.setdefault(rec.branch, f"live: worker {rec.worker_id} ({rec.state})")
    for reg in (read_registry(registry_path(root)), read_registry_at_ref(root, target, DEFAULT_TIMEOUT) or {}):
        for e in reg.get("entries") or []:
            if isinstance(e, dict) and e.get("branch") and e.get("codename") not in complete:
                held.setdefault(e["branch"], f"live: claimed by {e.get('node_id')}")
    for n in nodes:
        me = n.get("milestone_execution")
        if isinstance(me, dict) and me.get("state") != "closed" and me.get("rollup_branch"):
            held.setdefault(me["rollup_branch"], f"live: open rollup of {n.get('id')}")
    return held


def _worktrees(root: Path) -> list[dict[str, str]]:
    out = git_text(["worktree", "list", "--porcelain"], root) or ""
    blocks = []
    for chunk in out.split("\n\n"):
        wt = dict(line.partition(" ")[::2] for line in chunk.splitlines())
        if "worktree" in wt:
            blocks.append(wt)
    return blocks


def _worktree_reason(ctx: Any, wt: dict[str, str], merged_local: dict[str, bool]) -> tuple[str | None, bool]:
    """The reason to list it, and whether ``--fix`` may remove it (a detached one is judged after)."""
    if "prunable" in wt:
        return "directory missing", True
    branch = wt.get("branch", "").removeprefix("refs/heads/")
    if not branch:
        head = wt.get("HEAD", "")
        how = merged_how(ctx.root, head, ctx.target) if head else None
        if how == "merged":
            return f"branch gone: detached at {head[:12]}, which {ctx.target} contains", True
        if how:
            return f"branch gone: detached at {head[:12]}, {how}", True
        return f"detached at {head[:12]}", True
    if branch not in merged_local:
        return None, False
    if branch in ctx.held:
        return f"branch {branch} {ctx.held[branch]}", False
    if not merged_local[branch]:
        return f"branch {branch} has no commits yet", False
    return f"branch {branch} is merged", True


def _ignored_note(path: Path) -> str:
    """``git worktree remove`` deletes ignored files (``work/``…) without asking: say which."""
    if not path.is_dir():
        return ""
    out = git_text(["status", "--porcelain", "--ignored"], path) or ""
    ignored = [line[3:] for line in out.splitlines() if line.startswith("!! ")]
    return f"; removing it deletes ignored {', '.join(ignored)}" if ignored else ""


def _keep_detached(ctx: Any, wt: dict[str, str]) -> str | None:
    """Why ``--fix`` leaves a detached worktree: another command's, uncommitted changes, or a HEAD no ref holds."""
    if Path(wt["worktree"]).parent.name.startswith(TEMP_WORKTREES):
        return "a temporary worktree a running specy-road check may be using"
    if git_text(["status", "--porcelain"], Path(wt["worktree"])):
        return "uncommitted changes"
    refs = ["for-each-ref", "--count=1", "--contains", wt.get("HEAD", ""), "refs/heads", "refs/remotes"]
    if not git_text(refs, ctx.root):
        return "commits no branch holds"
    return None


def _remove_worktree(root: Path, path: str) -> str | None:
    code, out = git_code(["worktree", "remove", path], root)
    return out if code else None


def worktree_findings(ctx: Any, merged_local: dict[str, bool]) -> list[Finding]:
    """``merged_local``: local branches ``ctx.target`` contains -> whether each has a commit of its own."""
    here = Path(git_checked(["rev-parse", "--show-toplevel"], ctx.root)).resolve()
    found = []
    for wt in _worktrees(ctx.root)[1:]:   # the first is the main worktree
        path = wt["worktree"]
        if "locked" in wt or Path(path).resolve() == here:
            continue
        reason, fixable = _worktree_reason(ctx, wt, merged_local)
        if not reason:
            continue
        if not fixable:
            found.append(Finding("worktree", path, f"{reason}, so --fix leaves it", None, ""))
            continue
        keep = None if "branch" in wt else _keep_detached(ctx, wt)
        found.append(Finding(
            "worktree", path,
            reason + _ignored_note(Path(path)) + (f"; {keep}, so --fix leaves it" if keep else ""),
            None if keep else partial(_remove_worktree, ctx.root, path), f"removed worktree {path}",
        ))
    return found
