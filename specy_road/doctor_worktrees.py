"""``specy-road doctor``'s merged test, live-branch test and worktree findings.

A branch or worktree is *live* when an open registry claim (its leaf not Complete), an open
milestone rollup, a worker record that is not terminal or a live session holds it: doctor reports
it with that reason before anything else and never offers to remove it.

An ancestry-merged branch is offered for removal only with positive evidence, on that exact ref,
that it carried commits of its own (:func:`own_commit_evidence`): a fresh claim's tip is an
integration-branch commit, so ancestry alone would call it merged. Without evidence it is
reported, not removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable

from specy_road import session_presence, worker_state
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
NO_EVIDENCE = "no local evidence of own commits — remove by hand if intended"
#: Reflog subjects of entries that put a commit on the ref, and of entries that only name it.
_COMMIT_ENTRIES = ("commit", "merge ", "cherry-pick")
_NAMING_ENTRIES = ("branch: Created from", "Branch: renamed")


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


def _is_ancestor(root: Path, a: str, b: str) -> bool:
    return git_code(["merge-base", "--is-ancestor", a, b], root)[0] == 0


def _finish_merge_brought(root: Path, ref: str, tip: str, target: str) -> bool:
    """A ``Merge branch '<branch>'`` commit on ``target`` (finish-this-task's subject) brought ``tip`` in."""
    branch = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else ref.split("/", 3)[-1]
    log = git_text(["log", "--merges", "--fixed-strings", f"--grep=Merge branch '{branch}'",
                    "--format=%P", target], root) or ""
    for line in log.splitlines():
        first, *others = line.split()
        if not _is_ancestor(root, tip, first) and any(_is_ancestor(root, tip, p) for p in others):
            return True
    return False


def own_commit_evidence(root: Path, ref: str, target: str) -> str:
    """``"present"``, ``"absent"`` or ``"ambiguous"``: did ``ref`` itself carry commits of its own?

    Present: a finish merge commit on ``target`` brought this tip in, or this local ref's reflog has
    a commit, merge or cherry-pick entry whose commit its tip contains. Absent: this local ref's
    reflog holds only its creation and renames, all at its tip. Anything else (an expired reflog, a
    fresh clone, a remote-tracking ref, a reset) is ambiguous. Evidence is never borrowed from
    another ref, such as a remote ref's local namesake.
    """
    tip = git_text(["rev-parse", ref], root) or ""
    if tip and _finish_merge_brought(root, ref, tip, target):
        return "present"
    if not tip or not ref.startswith("refs/heads/"):
        return "ambiguous"
    entries = [line.split("\t", 1) for line in
               (git_text(["reflog", "show", "--format=%H%x09%gs", ref], root) or "").splitlines()]
    entries = [e for e in entries if len(e) == 2]
    if any(gs.startswith(_COMMIT_ENTRIES) and _is_ancestor(root, sha, tip) for sha, gs in entries):
        return "present"
    if entries and all(gs.startswith(_NAMING_ENTRIES) and sha == tip for sha, gs in entries):
        return "absent"
    return "ambiguous"


def live_holders(root: Path, target: str, nodes: list[dict[str, Any]],
                 complete: dict[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """``live: …`` by branch and by resolved worktree path: workers, live sessions, open claims, open rollups."""
    held: dict[str, str] = {}
    paths: dict[str, str] = {}
    running = [(f"live: worker {r.worker_id} ({r.state})", r.branch, r.worktree)
               for r in worker_state.list_records(root, active_only=True)]
    running += [(f"live: session {s.agent}", s.branch, s.worktree) for s in session_presence.list_sessions(root)]
    for why, branch, worktree in running:
        if branch:
            held.setdefault(branch, why)
        if worktree:
            paths.setdefault(str(Path(worktree).resolve()), why)
    for reg in (read_registry(registry_path(root)), read_registry_at_ref(root, target, DEFAULT_TIMEOUT) or {}):
        for e in reg.get("entries") or []:
            if isinstance(e, dict) and e.get("branch") and e.get("codename") not in complete:
                held.setdefault(e["branch"], f"live: claimed by {e.get('node_id')}")
    for n in nodes:
        me = n.get("milestone_execution")
        if isinstance(me, dict) and me.get("state") != "closed" and me.get("rollup_branch"):
            held.setdefault(me["rollup_branch"], f"live: open rollup of {n.get('id')}")
    return held, paths


def _worktrees(root: Path) -> list[dict[str, str]]:
    out = git_text(["worktree", "list", "--porcelain"], root) or ""
    blocks = []
    for chunk in out.split("\n\n"):
        wt = dict(line.partition(" ")[::2] for line in chunk.splitlines())
        if "worktree" in wt:
            blocks.append(wt)
    return blocks


#: Why the worktree of a merged branch is listed, by the branch's verdict (``_branch_reason``).
_MERGED_WORKTREE = {"merged": "is merged", "fresh": "has no commits yet", "unproven": f"is merged; {NO_EVIDENCE}"}


def _live_reason(ctx: Any, wt: dict[str, str]) -> str | None:
    branch = wt.get("branch", "").removeprefix("refs/heads/")
    if branch and branch in ctx.held:
        return f"branch {branch} {ctx.held[branch]}"
    return ctx.held_paths.get(str(Path(wt["worktree"]).resolve()))


def _worktree_reason(ctx: Any, wt: dict[str, str], merged_local: dict[str, str]) -> tuple[str | None, bool]:
    """The reason to list it, and whether ``--fix`` may remove it (a detached one is judged after).

    Liveness comes first, before a missing directory or a merged branch: a live worktree is
    reported with its live reason and never removed.
    """
    live = _live_reason(ctx, wt)
    branch = wt.get("branch", "").removeprefix("refs/heads/")
    if live:
        return (live, False) if "prunable" in wt or branch in merged_local or not branch else (None, False)
    if "prunable" in wt:
        return "directory missing", True
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
    return f"branch {branch} {_MERGED_WORKTREE[merged_local[branch]]}", merged_local[branch] == "merged"


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


def worktree_findings(ctx: Any, merged_local: dict[str, str]) -> list[Finding]:
    """``merged_local``: local branches ``ctx.target`` has -> ``"merged"``, ``"fresh"`` or ``"unproven"``."""
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
