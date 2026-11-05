"""``specy-road doctor``'s merged test, live-branch test and worktree findings.

A branch or worktree is *live* when an open registry claim (its leaf not Complete), an open
milestone rollup, a worker record that is not terminal or a live session holds it: doctor reports
it with that reason before anything else and never offers to remove it.

An ancestry-merged branch is offered for removal only with positive evidence, on that exact ref,
that it carried commits of its own (:func:`evidence_kind`): a fresh claim's tip is an
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
#: Reflog subjects of entries that put a commit on the ref, and of its creation events, by evidence kind.
#: A copy (``git branch -c``) or a rename's target starts with entries git carried over from another
#: ref: the newest creation event is a boundary, and nothing before it is this ref's evidence.
_COMMIT_ENTRIES = ("commit", "merge ", "cherry-pick")
_CREATIONS = {"branch: Created from": "creation-only", "Branch: copied": "copy-only",
              "Branch: renamed": "rename-only"}


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


def _finish_merge_brought(root: Path, branch: str, tip: str, target: str) -> bool:
    """A ``Merge branch '<branch>'`` commit on ``target`` (finish-this-task's subject) brought ``tip`` in."""
    log = git_text(["log", "--merges", "--fixed-strings", f"--grep=Merge branch '{branch}'",
                    "--format=%P", target], root) or ""
    for line in log.splitlines():
        first, *others = line.split()
        if not merged_into(root, tip, first) and any(merged_into(root, tip, p) for p in others):
            return True
    return False


def _since_creation(root: Path, local: str) -> tuple[list[tuple[str, str]], str | None]:
    """``local``'s reflog entries (sha, subject), newest first, back to its newest creation event, and
    that event's evidence kind (``None`` when there is none: an expired reflog)."""
    out = git_text(["reflog", "show", "--format=%H%x09%gs", local], root) or ""
    entries = [(sha, gs) for sha, _, gs in (line.partition("\t") for line in out.splitlines())]
    for i, (_sha, gs) in enumerate(entries):
        for subject, kind in _CREATIONS.items():
            if gs.startswith(subject):
                return entries[: i + 1], kind
    return entries, None


def evidence_kind(root: Path, ref: str, target: str) -> str:
    """Own-commit evidence for exactly ``ref``: one of :data:`EVIDENCE` (A2).

    A local ref reads only its own reflog after its newest creation event (create, copy or rename
    target): a commit, merge or cherry-pick entry there that its tip contains is ``commit``; only the
    creation event at the tip is that event's kind (``creation-only``, ``copy-only``,
    ``rename-only``), which beats any finish merge an earlier branch of the same name left.
    A remote-tracking ref's evidence comes only from the remote-applicable source, a finish merge
    on ``target`` that brought its tip in (``finish-merge``), never from a local namesake's reflog,
    which can neither prove nor disprove anything about it; otherwise ``none``.
    """
    tip = git_text(["rev-parse", ref], root) or ""
    local = ref if ref.startswith("refs/heads/") else f"refs/heads/{ref.split('/', 3)[-1]}"
    if not tip:
        return "none"
    if ref == local:
        seg, created = _since_creation(root, local)
        if any(gs.startswith(_COMMIT_ENTRIES) and merged_into(root, sha, tip) for sha, gs in seg):
            return "commit"
        if created and seg == [(tip, seg[0][1])]:   # the creation event alone, at the tip
            return created
    if _finish_merge_brought(root, local.removeprefix("refs/heads/"), tip, target):
        return "finish-merge"
    return "none"


#: Inputs of :data:`CLASSIFICATION`, in order.
LIVE_SOURCES = ("claim", "worker", "session", "none")   # precedence of the live reason (A1)
EVIDENCE = ("commit", "finish-merge", "creation-only", "copy-only", "rename-only", "none")
CONTAINMENT = ("yes", "no", "same-patch")   # merged_how: "merged", None, SAME_PATCH
REF_KINDS = ("local", "remote")
#: (live source, evidence, containment, ref kind) -> (label, fix offered). ``*`` matches anything;
#: the first matching row wins. Every branch and worktree-on-a-branch verdict comes from here.
CLASSIFICATION: tuple[tuple[tuple[str, str, str, str], tuple[str, bool]], ...] = (
    (("claim", "*", "*", "*"), ("live", False)),
    (("worker", "*", "*", "*"), ("live", False)),
    (("session", "*", "*", "*"), ("live", False)),
    (("none", "creation-only", "*", "*"), ("no commits yet", False)),
    (("none", "copy-only", "*", "*"), ("no commits yet", False)),   # F1: a copy's inherited entries
    (("none", "rename-only", "*", "*"), ("no commits yet", False)),
    (("none", "commit", "yes", "*"), ("merged", True)),
    (("none", "finish-merge", "yes", "remote"), ("merged", True)),   # F2: a remote's only evidence source
    (("none", "finish-merge", "yes", "local"), ("merged", True)),
    (("none", "none", "yes", "*"), ("merged, no evidence", False)),   # A3's deliberate change
    (("none", "*", "same-patch", "*"), ("same patch", True)),   # a tip outside target: commits by construction
    (("none", "*", "no", "*"), ("not merged", True)),   # unchanged: an unclaimed unmerged branch with commits
)


def classify(live: str, evidence: str, containment: str, ref_kind: str) -> tuple[str, bool]:
    key = (live, evidence, containment, ref_kind)
    for row, verdict in CLASSIFICATION:
        if all(want in ("*", got) for want, got in zip(row, key)):
            return verdict
    raise ValueError(f"no classification row for {key}")


def containment(how: str | None) -> str:
    return "yes" if how == "merged" else "same-patch" if how else "no"


def live_holders(root: Path, target: str, nodes: list[dict[str, Any]], complete: dict[str, str]
                 ) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    """(source, ``live: …``) by branch and by resolved worktree path, claim before worker before session.

    Claims are open registry rows (leaf not Complete) and open milestone rollups.
    """
    held: dict[str, tuple[str, str]] = {}
    paths: dict[str, tuple[str, str]] = {}
    for reg in (read_registry(registry_path(root)), read_registry_at_ref(root, target, DEFAULT_TIMEOUT) or {}):
        for e in reg.get("entries") or []:
            if isinstance(e, dict) and e.get("branch") and e.get("codename") not in complete:
                held.setdefault(e["branch"], ("claim", f"live: claimed by {e.get('node_id')}"))
    for n in nodes:
        me = n.get("milestone_execution")
        if isinstance(me, dict) and me.get("state") != "closed" and me.get("rollup_branch"):
            held.setdefault(me["rollup_branch"], ("claim", f"live: open rollup of {n.get('id')}"))
    running = [("worker", f"live: worker {r.worker_id} ({r.state})", r.branch, r.worktree)
               for r in worker_state.list_records(root, active_only=True)]
    running += [("session", f"live: session {s.agent}", s.branch, s.worktree)
                for s in session_presence.list_sessions(root)]
    for source, why, branch, worktree in running:
        if branch:
            held.setdefault(branch, (source, why))
        if worktree:
            paths.setdefault(str(Path(worktree).resolve()), (source, why))
    return held, paths


def _worktrees(root: Path) -> list[dict[str, str]]:
    out = git_text(["worktree", "list", "--porcelain"], root) or ""
    blocks = []
    for chunk in out.split("\n\n"):
        wt = dict(line.partition(" ")[::2] for line in chunk.splitlines())
        if "worktree" in wt:
            blocks.append(wt)
    return blocks


#: How a worktree on a local branch reads, by the branch's label; a label not here is not listed.
_WORKTREE_TEXT = {"merged": "is merged", "same patch": "is merged", "no commits yet": "has no commits yet",
                  "merged, no evidence": f"is merged; {NO_EVIDENCE}"}


def _live(ctx: Any, wt: dict[str, str], branch: str) -> tuple[str, str]:
    """(source, reason) of the highest-precedence holder of the worktree, by branch or by path."""
    found = []
    if branch in ctx.held:
        source, why = ctx.held[branch]
        found.append((source, f"branch {branch} {why}"))
    if (by_path := ctx.held_paths.get(str(Path(wt["worktree"]).resolve()))):
        found.append(by_path)
    return min(found, key=lambda f: LIVE_SOURCES.index(f[0])) if found else ("none", "")


def _worktree_reason(ctx: Any, wt: dict[str, str], local: dict[str, tuple[str, str]]) -> tuple[str | None, bool]:
    """The reason to list it, and whether ``--fix`` may remove it (a detached one is judged after).

    Liveness comes first, before a missing directory: a live worktree is reported with its live
    reason and never removed. It is listed only when it would be listed were it not live.
    """
    branch = wt.get("branch", "").removeprefix("refs/heads/")
    source, live_why = _live(ctx, wt, branch)
    evidence, contained = local.get(branch, ("none", "no"))
    label, fix = classify(source, evidence, contained, "local")
    listed = "prunable" in wt or not branch or classify("none", evidence, contained, "local")[0] in _WORKTREE_TEXT
    if label == "live":
        return (live_why, False) if listed else (None, False)
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
    if label not in _WORKTREE_TEXT:
        return None, False
    return f"branch {branch} {_WORKTREE_TEXT[label]}", fix


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


def worktree_findings(ctx: Any, local: dict[str, tuple[str, str]]) -> list[Finding]:
    """``local``: each local ``feature/rm-*`` branch -> (evidence, containment), the inputs of :func:`classify`."""
    here = Path(git_checked(["rev-parse", "--show-toplevel"], ctx.root)).resolve()
    found = []
    for wt in _worktrees(ctx.root)[1:]:   # the first is the main worktree
        path = wt["worktree"]
        if "locked" in wt or Path(path).resolve() == here:
            continue
        reason, fixable = _worktree_reason(ctx, wt, local)
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
