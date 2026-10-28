"""Resolve what a review is about: node, branch, commit under review, and base.

Shared by ``review-packet``, ``handoff status``, ``review record``, and the
``mark-implementation-reviewed`` gate so all four agree on which commit a review
binds to.

The commit under review is the tip of the node's registered feature branch —
the local branch, else its remote-tracking ref — minus trailing registry-only
bookkeeping commits. Reading the branch tip instead of checking it out matters:
a coordinator in a checkout shared with executors must not switch branches
(proposal §3.4). A registered branch that exists nowhere is an error, never a
silent fall back to ``HEAD``.
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

    @property
    def node_id(self) -> str:
        return self.node["id"]

    @property
    def touch_zones(self) -> list[str]:
        entry = self.entry or {}
        return list(entry.get("touch_zones") or self.node.get("touch_zones") or [])


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
            " — review-packet and review record also take --ref <branch or commit>"
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
    span = [f"{base}..{tip}"] if base else ["-n", "20", tip]
    shas = (git_text(["log", "--first-parent", "--format=%H", *span], repo_root) or "").split()
    for sha in shas:
        # Any merge is new work, even one whose tree equals its first parent:
        # `git merge -s ours` changes nothing here yet decides what lands.
        if full_sha(repo_root, f"{sha}^2") or _changed_by(repo_root, sha) not in ([], [REGISTRY_REL]):
            return sha
    return tip


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
    use_ref = ref or default_ref(repo_root, entry or {"node_id": node_id}, remote)
    if not full_sha(repo_root, use_ref):
        raise ReviewTargetError(f"cannot resolve {use_ref!r} to a commit")
    bref = base_ref(repo_root, remote, ib)
    base = git_text(["merge-base", bref, use_ref], repo_root) if bref else None
    commit = reviewed_commit(repo_root, use_ref, base)
    return ReviewTarget(node, nodes, entry, use_ref, commit, bref, base)


def resolve_target_or_exit(repo_root: Path, node_id: str, ref: str | None = None) -> ReviewTarget:
    try:
        return resolve_target(repo_root, node_id, ref)
    except ReviewTargetError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e
