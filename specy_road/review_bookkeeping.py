"""Whether a later commit is only this leaf's planning sheet or review bookkeeping."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_code, git_text
from specy_road.review_files import REVIEWS_REL, ReviewFile
from specy_road.runtime_paths import project_prefix, rebase_to_project
from specy_road.review_target import same_commit

CARRY_NOTE = "; approvals still count (only planning or review bookkeeping changed since the reviewed commit)"


def only_planning_or_review_bookkeeping_since(
    repo_root: Path, node: dict[str, Any], approved: str, commit: str | None,
) -> bool:
    """True when every path in ``approved..commit`` is this leaf's sheet or review bookkeeping.

    False when ``commit`` is missing, the range is not ancestral, it contains a merge
    (including ``git merge -s ours``), or any other path changed.
    """
    if not commit:
        return False
    if git_code(["merge-base", "--is-ancestor", approved, commit], repo_root)[0] != 0:
        return False
    if git_text(["rev-list", "--merges", f"{approved}..{commit}"], repo_root):
        return False
    paths = diff_paths(repo_root, f"{approved}..{commit}")
    if paths is None:
        return False
    pd = (node.get("planning_dir") or "").strip().strip("/")
    if not pd:
        return False
    prefix = project_prefix(repo_root)
    summary = f"work/implementation-summary-{node['id']}.md"
    handoffs = f"{REVIEWS_REL.as_posix()}/{node['id']}"
    for p in paths:
        rel = rebase_to_project(p, prefix)
        if rel is None:
            return False
        if rel not in (pd, summary) and rel != handoffs and not rel.startswith(f"{handoffs}/"):
            return False
    return True


def count_at_later_commit(result: Any, repo_root: Path, node: dict[str, Any], review: ReviewFile) -> bool:
    """False when ``review`` is stale at ``result.commit`` (appended to ``result.stale``)."""
    if same_commit(repo_root, review.data["commit"], result.commit):
        return True
    if only_planning_or_review_bookkeeping_since(repo_root, node, review.data["commit"], result.commit):
        result.bookkeeping_carry = True
        return True
    result.stale.append(review)
    return False
