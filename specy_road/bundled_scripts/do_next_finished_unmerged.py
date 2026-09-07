"""Leaves already finished on a feature branch the integration branch has not merged.

Pickup's only defence against claiming such a leaf twice is its registry row,
and the row is the part most likely to be gone: ``abort-task-pickup`` removes
it, F-014 self-heal removes it, and a hand-edited registry can drop it. The
branch outlives the row — a claim is released without deleting the branch on
every one of those paths — so the branch tip is the durable record that the
work was done.

This is not specific to ``on_complete: pr``. A node's own tier in
:func:`_available` is read from its ``status`` in the integration-branch graph,
never from the ``status_overrides`` that carry feature-tip Complete, so no mode
consults the tip for the finished node itself. ``pr`` only makes it easy to
reach, because the gap between "finished" and "merged" is a human PR review.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.git_subprocess import git_ok

FEATURE_PREFIX = "feature/rm-"


def feature_refs_by_codename(repo_root: Path, remote: str) -> dict[str, str]:
    """``codename -> ref`` for every ``feature/rm-*`` branch this clone can see.

    A local head wins over its remote-tracking ref. ``finish-this-task`` commits
    bookkeeping locally and pushes separately, so when both exist the local tip
    is the one that already knows the node is Complete.
    """
    ok, out = git_ok(
        [
            "for-each-ref",
            "--format=%(refname:short)",
            f"refs/heads/{FEATURE_PREFIX}*",
            f"refs/remotes/{remote}/{FEATURE_PREFIX}*",
        ],
        repo_root,
    )
    if not ok:
        return {}
    refs: dict[str, str] = {}
    for line in out.splitlines():
        ref = line.strip()
        idx = ref.find(FEATURE_PREFIX)
        if idx < 0:
            continue
        codename = ref[idx + len(FEATURE_PREFIX) :]
        if not codename:
            continue
        is_local = not ref.startswith(f"{remote}/")
        if is_local or codename not in refs:
            refs[codename] = ref
    return refs


def finished_unmerged_ids(
    candidates: list[dict],
    *,
    repo_root: Path,
    remote: str,
    integration_branch: str,
) -> tuple[set[str], list[str]]:
    """Candidate ids whose own ``feature/rm-<codename>`` tip already says Complete.

    Returns the ids to drop and one explanatory line each. Only candidates are
    inspected, and only those whose branch exists, so the cost is one
    ``for-each-ref`` plus one graph read per branch actually in the way.
    """
    if not candidates:
        return set(), []
    refs = feature_refs_by_codename(repo_root, remote)
    if not refs:
        return set(), []

    nodes_at_ref: dict[str, list[dict] | None] = {}
    finished: set[str] = set()
    logs: list[str] = []
    for node in candidates:
        codename = node.get("codename")
        node_id = node.get("id")
        if not isinstance(codename, str) or not codename:
            continue
        if not isinstance(node_id, str) or not node_id:
            continue
        ref = refs.get(codename)
        if ref is None:
            continue
        if ref not in nodes_at_ref:
            nodes_at_ref[ref] = load_roadmap_nodes_at_ref(repo_root, ref)
        nodes = nodes_at_ref[ref]
        if not nodes:
            continue
        matched = next((n for n in nodes if n.get("id") == node_id), None)
        if matched is None:
            continue
        if (matched.get("status") or "").lower() != "complete":
            continue
        finished.add(node_id)
        logs.append(
            f"[info] skipping {node_id} ({codename}): already Complete on {ref}, "
            f"which {integration_branch} has not merged. Land that branch to close "
            f"the node, or delete it to redo the work."
        )
    return finished, logs
