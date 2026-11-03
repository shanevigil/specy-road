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

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.roadmap_chunk_utils import find_chunk_path
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.finish_implementation_check import base_ref
from specy_road.git_subprocess import git_stdout, git_text, local_branch_exists
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.roadmap_json import nodes_from_chunk_doc
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
    unfinished_leaves: list[str] = field(default_factory=list)   # leaves not Complete at ``commit`` (milestone)
    committed_zones: list[str] | None = None   # the node's touch_zones at ``commit``; None = not readable there

    @property
    def node_id(self) -> str:
        return self.node["id"]

    @property
    def touch_zones(self) -> list[str]:
        entry = self.entry or {}
        return list(entry.get("touch_zones") or self.node.get("touch_zones") or [])

    @property
    def review_zones(self) -> list[str]:
        """The zones a review judges against: the claim row's plus the node's as committed at ``commit``.

        Zones added to the node on the feature branch count although the
        checkout building the packet has not seen that commit; when the node
        cannot be read there, :attr:`touch_zones` stands.
        """
        if self.committed_zones is None:
            return self.touch_zones
        claimed = (self.entry or {}).get("touch_zones") or []
        return list(dict.fromkeys([*claimed, *self.committed_zones]))

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


def node_at(repo_root: Path, node_id: str, commit: str | None) -> dict[str, Any] | None:
    """``node_id`` as its chunk **at ``commit``** records it; ``None`` when it cannot be read there.

    The chunk is the one holding the node in the working tree, read from git
    at ``commit``, so a checkout on another branch sees what that commit says.
    """
    chunk = find_chunk_path(repo_root, node_id) if commit else None
    rel = chunk.relative_to(repo_root.resolve()) if chunk else None
    text = rel is not None and git_stdout(["show", f"{commit}:./{rel.as_posix()}"], repo_root)
    try:
        nodes = nodes_from_chunk_doc(json.loads(text)) if text else None
    except ValueError:
        nodes = None
    return next((n for n in nodes or [] if n.get("id") == node_id), None)


def _zones_at(repo_root: Path, node_id: str, commit: str | None) -> list[str] | None:
    node = node_at(repo_root, node_id, commit)
    return None if node is None else list(node.get("touch_zones") or [])


def unfinished_leaves_at(repo_root: Path, nodes: list[dict[str, Any]], node_id: str, commit: str) -> list[str]:
    """Leaves under ``node_id`` whose chunk **at ``commit``** does not say Complete.

    The working tree says what the finishing branch knows; the integration tip
    says what has landed. A leaf whose chunk cannot be read there counts as
    unfinished: the review must cover the landed change.
    """
    return [leaf["id"] for leaf in leaf_descendants(nodes, node_id)
            if (node_at(repo_root, leaf["id"], commit) or {}).get("status") != "Complete"]


def resolve_target(
    repo_root: Path, node_id: str, ref: str | None = None, *, nodes: list[dict[str, Any]] | None = None
) -> ReviewTarget:
    """Build the target for ``node_id``; raises :class:`ReviewTargetError`.

    ``nodes`` is the already-loaded graph when the caller has one: the public
    loader applies the milestone-review hold, so a nested ``load_roadmap``
    here would recurse.
    """
    nodes = list(nodes) if nodes is not None else load_roadmap(repo_root)["nodes"]
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
                            milestone_review_base(repo_root, nodes, node_id, tip), milestone=True,
                            unfinished_leaves=unfinished_leaves_at(repo_root, nodes, node_id, tip),
                            committed_zones=_zones_at(repo_root, node_id, tip))
    use_ref = ref or default_ref(repo_root, entry or {"node_id": node_id}, remote)
    if not full_sha(repo_root, use_ref):
        raise ReviewTargetError(f"cannot resolve {use_ref!r} to a commit")
    base = git_text(["merge-base", bref, use_ref], repo_root) if bref else None
    commit = reviewed_commit(repo_root, use_ref, base)
    return ReviewTarget(node, nodes, entry, use_ref, commit, bref, base,
                        committed_zones=_zones_at(repo_root, node_id, commit))


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
    if t.unfinished_leaves:
        return "leaves_open", [milestone_open_problem(t) or ""]
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


def milestone_open_problem(t: ReviewTarget) -> str | None:
    """Why the full review cannot start: a leaf has not landed at the commit under review."""
    if t.milestone and t.unfinished_leaves:
        return (f"{t.node_id}: leaves {', '.join(t.unfinished_leaves)} are not Complete at {t.ref} "
                f"({(t.commit or '?')[:12]}); its full review starts when the last one lands")
    return None


def milestone_packet_or_exit(t: ReviewTarget) -> None:
    """``review-packet`` needs every leaf landed and the milestone's start (a leaf registration, or ``--base``)."""
    why = milestone_open_problem(t)
    if why is None and t.milestone and not t.base:
        why = (f"no 'register as in-progress' commit of a leaf under {t.node_id} is reachable from {t.ref}, "
               "so the milestone's combined change has no start; pass --base <the commit before its first leaf>")
    if why:
        print(f"error: {why}", file=sys.stderr)
        raise SystemExit(1)


def milestone_close_problem(repo_root: Path, t: ReviewTarget) -> str | None:
    """Why ``mark-implementation-reviewed <MILESTONE_ID>`` must not write: open leaves, or the wrong checkout.

    Closure commits to the checked-out branch, so that must be the integration
    branch with ``HEAD`` at the commit whose gate passed; a local branch behind
    or ahead of the reviewed tip would commit a status the review did not cover.
    """
    why = milestone_open_problem(t)
    if why:
        return why
    ib, _remote, _warn = resolve_integration_defaults(repo_root, explicit_base=None, explicit_remote=None)
    branch = git_text(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    if branch != ib:
        return (f"the checked-out branch is {branch!r}, not the integration branch {ib!r}; closure commits "
                "the milestone's status there, so run it from that checkout")
    if not same_commit(repo_root, "HEAD", t.commit):
        return (f"HEAD ({(full_sha(repo_root, 'HEAD') or '?')[:12]}) is not the reviewed commit "
                f"{(t.commit or '?')[:12]} ({t.ref}); pull or push so they agree, then re-check the gate")
    return None
