"""Resolve what a review is about: node, branch, commit under review, and base.

Shared by ``review-packet``, ``prompt``, ``handoff status``, ``review record``,
``review list``, and the ``mark-implementation-reviewed`` gate so all of them
agree on which commit a review binds to.

The commit under review is the tip of the node's registered feature branch —
the local branch, else its remote-tracking ref — minus trailing registry-only
bookkeeping commits. Reading the branch tip instead of checking it out matters:
a coordinator in a checkout shared with executors must not switch branches
(proposal §3.4). A registered branch that exists nowhere is an error, never a
silent fall back to ``HEAD``.

A **milestone** (a node with leaf children) has no claim: its full review
targets the integration tip, and its base is the first parent of the oldest
``register as in-progress`` commit of any leaf under it that the tip reaches,
so the diff is the milestone's combined change (:func:`milestone_review_base`).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.finish_implementation_check import base_ref
from specy_road.git_subprocess import git_text, local_branch_exists
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.runtime_paths import project_prefix

REGISTRY_REL = "roadmap/registry.yaml"


class ReviewTargetError(Exception):
    """The node, branch, or commit to review cannot be resolved."""


@dataclass
class ReviewTarget:
    node: dict[str, Any]
    nodes: list[dict[str, Any]]
    entry: dict[str, Any] | None
    ref: str
    commit: str | None
    base_ref: str | None
    base: str | None
    milestone: bool = False   # reviewed as a whole at the integration tip, not as a claimed leaf

    @property
    def node_id(self) -> str:
        return self.node["id"]

    @property
    def touch_zones(self) -> list[str]:
        entry = self.entry or {}
        return list(entry.get("touch_zones") or self.node.get("touch_zones") or [])

    @property
    def leaf_ids(self) -> list[str]:
        return [n["id"] for n in leaf_descendants(self.nodes, self.node_id)]


def full_sha(repo_root: Path, rev: str | None) -> str | None:
    """Full object id of the commit ``rev`` names, or ``None`` (unknown or ambiguous)."""
    if not rev:
        return None
    return git_text(["rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"], repo_root) or None


def same_commit(repo_root: Path, a: str | None, b: str | None) -> bool:
    """Whether ``a`` and ``b`` resolve, through git, to one commit object."""
    fa = full_sha(repo_root, a)
    return fa is not None and fa == full_sha(repo_root, b)


def _registry_entry(repo_root: Path, node_id: str) -> dict[str, Any] | None:
    entries = read_registry(registry_path(repo_root)).get("entries") or []
    return next((e for e in entries if e.get("node_id") == node_id), None)


def default_ref(repo_root: Path, entry: dict[str, Any] | None, remote: str) -> str:
    """The registered branch: local first, then ``<remote>/<branch>``."""
    branch = (entry or {}).get("branch")
    if not branch:
        node = (entry or {}).get("node_id", "this node")
        raise ReviewTargetError(
            f"no registry claim for {node}; pick it up first (`specy-road do-next-available-task --under {node}`)"
            " — review-packet, review record, review list and prompt also take --ref <branch or commit>"
        )
    if local_branch_exists(repo_root, branch):
        return branch
    tracking = f"refs/remotes/{remote}/{branch}"
    if full_sha(repo_root, tracking):
        return f"{remote}/{branch}"
    raise ReviewTargetError(
        f"registered branch {branch!r} is neither a local branch nor {remote}/{branch}; "
        "run git fetch, or pass --ref"
    )


def _changed_by(repo_root: Path, sha: str) -> list[str]:
    """Paths a commit changed relative to its first parent (all paths for a root).

    ``git diff-tree <merge>`` prints nothing for a merge commit, which would make
    any merge look like bookkeeping; diffing against the first parent counts
    what the merge brought onto this branch, conflict resolutions included.
    """
    if full_sha(repo_root, f"{sha}^1"):
        out = git_text(["diff", "--name-only", f"{sha}^1", sha], repo_root)
    else:
        out = git_text(["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha], repo_root)
    return (out or "").split()


def reviewed_commit(repo_root: Path, ref: str, base: str | None) -> str | None:
    """The newest commit on ``ref`` that changed more than ``roadmap/registry.yaml``.

    Claim bookkeeping — the registration commit, and the commit
    ``mark-implementation-reviewed`` itself writes — touches only the registry.
    Skipping those keeps a review bound to the implementation it read, so the
    gate's own commit does not turn every review stale. Falls back to the tip
    when nothing past ``base`` changed real files.
    """
    tip = full_sha(repo_root, ref)
    if not tip:
        return None
    # git names changed paths from the repository root; the registry sits
    # under the project prefix in the nested layout.
    registry = project_prefix(repo_root) + REGISTRY_REL
    span = [f"{base}..{tip}"] if base else ["-n", "20", tip]
    shas = (git_text(["log", "--first-parent", "--format=%H", *span], repo_root) or "").split()
    for sha in shas:
        # Any merge is new work, even one whose tree equals its first parent:
        # `git merge -s ours` changes nothing here yet decides what lands.
        if full_sha(repo_root, f"{sha}^2") or _changed_by(repo_root, sha) not in ([], [registry]):
            return sha
    return tip


def leaf_descendants(nodes: list[dict[str, Any]], node_id: str) -> list[dict[str, Any]]:
    """The leaves under ``node_id`` (nodes with no children), in graph order."""
    children: dict[str, list[dict[str, Any]]] = {}
    for n in nodes:
        if isinstance(n.get("parent_id"), str):
            children.setdefault(n["parent_id"], []).append(n)
    out: list[dict[str, Any]] = []
    stack = list(reversed(children.get(node_id, [])))
    while stack:
        n = stack.pop()
        kids = children.get(n.get("id"), [])
        if kids:
            stack.extend(reversed(kids))
        else:
            out.append(n)
    return out


def is_milestone(nodes: list[dict[str, Any]], node_id: str) -> bool:
    """A node reviewed as a whole: it has at least one leaf child of its own."""
    children: dict[str, int] = {}
    for n in nodes:
        if isinstance(n.get("parent_id"), str):
            children[n["parent_id"]] = children.get(n["parent_id"], 0) + 1
    return any(n.get("parent_id") == node_id and n.get("id") not in children for n in nodes)


REGISTER_SUBJECT = "register as in-progress"   # pickup's bookkeeping commit: chore(rm-<codename>): ...


def milestone_review_base(repo_root: Path, nodes: list[dict[str, Any]], node_id: str, tip: str) -> str | None:
    """Where the milestone's combined change starts: the first parent of the oldest leaf registration.

    Each leaf's pickup commits ``chore(rm-<codename>): register as in-progress``
    on its branch from the integration point it started at, so that commit's
    first parent is the leaf's branch point. With several leaves the common
    ancestor of their branch points is the earliest one. ``None`` when no leaf
    under ``node_id`` has such a commit reachable from ``tip``.
    """
    codenames = {n.get("codename") for n in leaf_descendants(nodes, node_id) if n.get("codename")}
    wanted = {f"chore(rm-{c}): {REGISTER_SUBJECT}" for c in codenames}
    log = git_text(["log", "--format=%H %s", f"--grep={REGISTER_SUBJECT}", "--fixed-strings", tip], repo_root) or ""
    parents = []
    for line in log.splitlines():
        sha, _, subject = line.partition(" ")
        if any(subject.startswith(w) for w in wanted):
            parent = full_sha(repo_root, f"{sha}^1")
            if parent and parent not in parents:
                parents.append(parent)
    if not parents:
        return None
    if len(parents) == 1:
        return parents[0]
    return git_text(["merge-base", "--octopus", *parents], repo_root) or None


def resolve_target(repo_root: Path, node_id: str, ref: str | None = None) -> ReviewTarget:
    """Build the target for ``node_id``; raises :class:`ReviewTargetError`."""
    nodes = load_roadmap(repo_root)["nodes"]
    node = next((n for n in nodes if n.get("id") == node_id), None)
    if node is None:
        raise ReviewTargetError(f"unknown node id: {node_id}")
    entry = _registry_entry(repo_root, node_id)
    ib, remote, _warn = resolve_integration_defaults(
        repo_root, explicit_base=None, explicit_remote=None
    )
    bref = base_ref(repo_root, remote, ib)
    if is_milestone(nodes, node_id) and not (entry or {}).get("branch"):
        use_ref = ref or bref
        if use_ref is None:
            raise ReviewTargetError(
                f"{node_id} is a milestone: its full review targets the integration branch {ib!r}, "
                "which is neither local nor remote-tracking; run git fetch, or pass --ref"
            )
        tip = full_sha(repo_root, use_ref)
        if tip is None:
            raise ReviewTargetError(f"cannot resolve {use_ref!r} to a commit")
        return ReviewTarget(node, nodes, entry, use_ref, tip, bref,
                            milestone_review_base(repo_root, nodes, node_id, tip), milestone=True)
    use_ref = ref or default_ref(repo_root, entry or {"node_id": node_id}, remote)
    if not full_sha(repo_root, use_ref):
        raise ReviewTargetError(f"cannot resolve {use_ref!r} to a commit")
    base = git_text(["merge-base", bref, use_ref], repo_root) if bref else None
    commit = reviewed_commit(repo_root, use_ref, base)
    return ReviewTarget(node, nodes, entry, use_ref, commit, bref, base)


def resolve_target_or_exit(repo_root: Path, node_id: str, ref: str | None = None) -> ReviewTarget:
    try:
        return resolve_target(repo_root, node_id, ref)
    except ReviewTargetError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e


# --- Milestone full review: what every command says about it (policy.milestone_full_review) ---

MILESTONE_SUMMARY = "_A milestone has no implementation summary: each leaf's was reviewed with that leaf._"


def milestone_status(t: ReviewTarget, state: str) -> tuple[str, list[str]]:
    """``(state, next-step lines)`` for ``handoff status`` and ``review list``; unchanged for a leaf.

    A finished milestone whose gate is not met is ``awaiting_full_review``; a
    Complete one is ``complete_no_claim``, like a leaf whose claim is released.
    """
    if not t.milestone:
        return state, []
    if t.node.get("status") == "Complete":
        return "complete_no_claim", []
    if state not in ("approved", "blocked", "escalated"):
        state = "awaiting_full_review"
    if state == "approved":
        return state, [f"milestone full review met: specy-road mark-implementation-reviewed {t.node_id} sets it Complete"]
    return state, [f"milestone full review pending (policy.milestone_full_review): specy-road review-packet {t.node_id}; "
                   f"approval releases the rollup with specy-road mark-implementation-reviewed {t.node_id}"]


def milestone_packet_lines(t: ReviewTarget) -> list[str]:
    """The packet header line naming the leaves a milestone's combined change covers."""
    if not t.milestone:
        return []
    ids = ", ".join(f"`{i}`" for i in t.leaf_ids) or "none"
    return [f"- **Milestone full review:** the combined change of its leaves ({ids}) from the first leaf's branch "
            f"point to the integration tip (`policy.milestone_full_review`); approval closes it with "
            f"`specy-road mark-implementation-reviewed {t.node_id}`"]


def milestone_base_or_exit(t: ReviewTarget) -> None:
    """``review-packet`` needs the milestone's start; without a leaf registration only ``--base`` gives one."""
    if t.milestone and not t.base:
        print(f"error: no 'register as in-progress' commit of a leaf under {t.node_id} is reachable from {t.ref}, "
              "so the milestone's combined change has no start; pass --base <the commit before its first leaf>",
              file=sys.stderr)
        raise SystemExit(1)
