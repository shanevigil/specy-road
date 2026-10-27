"""Resolve what a review is about: node, branch, commit under review, and base.

Shared by ``review-packet``, ``handoff status``, ``review record``, and the
``mark-implementation-reviewed`` gate so all four agree on which commit a review
binds to.

The commit under review is the tip of the node's registered feature branch when
that branch exists locally, else ``HEAD``. Reading the branch tip instead of
checking it out matters: a coordinator in a checkout shared with executors must
not switch branches (proposal §3.4).
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


def _registry_entry(repo_root: Path, node_id: str) -> dict[str, Any] | None:
    entries = read_registry(registry_path(repo_root)).get("entries") or []
    return next((e for e in entries if e.get("node_id") == node_id), None)


def default_ref(repo_root: Path, entry: dict[str, Any] | None) -> str:
    branch = (entry or {}).get("branch")
    if branch and local_branch_exists(repo_root, branch):
        return branch
    return "HEAD"


def reviewed_commit(repo_root: Path, ref: str, base: str | None) -> str | None:
    """The newest commit on ``ref`` that changed more than ``roadmap/registry.yaml``.

    Claim bookkeeping — the registration commit, and the commit
    ``mark-implementation-reviewed`` itself writes — touches only the registry.
    Skipping those keeps a review bound to the implementation it read, so the
    gate's own commit does not turn every review stale. Falls back to the tip
    when nothing past ``base`` changed real files.
    """
    tip = git_text(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo_root)
    if not tip:
        return None
    span = [f"{base}..{tip}"] if base else ["-n", "20", tip]
    shas = (git_text(["log", "--first-parent", "--format=%H", *span], repo_root) or "").split()
    for sha in shas:
        paths = git_text(["diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha], repo_root)
        if (paths or "").split() not in ([], [REGISTRY_REL]):
            return sha
    return tip


def resolve_target(repo_root: Path, node_id: str, ref: str | None = None) -> ReviewTarget:
    """Build the target for ``node_id``, or exit 1 when the node is unknown."""
    nodes = load_roadmap(repo_root)["nodes"]
    node = next((n for n in nodes if n.get("id") == node_id), None)
    if node is None:
        print(f"error: unknown node id: {node_id}", file=sys.stderr)
        raise SystemExit(1)
    entry = _registry_entry(repo_root, node_id)
    use_ref = ref or default_ref(repo_root, entry)
    ib, remote, _warn = resolve_integration_defaults(
        repo_root, explicit_base=None, explicit_remote=None
    )
    bref = base_ref(repo_root, remote, ib)
    has_ref = git_text(["rev-parse", "--verify", "--quiet", f"{use_ref}^{{commit}}"], repo_root)
    base = git_text(["merge-base", bref, use_ref], repo_root) if bref and has_ref else None
    commit = reviewed_commit(repo_root, use_ref, base)
    return ReviewTarget(node, nodes, entry, use_ref, commit, bref, base)


def same_commit(a: str | None, b: str | None) -> bool:
    """Whether two SHAs name the same commit; either may be abbreviated (min 7)."""
    if not a or not b or min(len(a), len(b)) < 7:
        return False
    return a.startswith(b) or b.startswith(a)
