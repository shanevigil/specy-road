"""Whether a later commit is only this leaf's planning sheet or review bookkeeping."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_code, git_text
from specy_road.review_files import REVIEWS_REL, ReviewFile
from specy_road.runtime_paths import project_prefix, rebase_to_project
from specy_road.review_target import same_commit
from specy_road.sibling_repos import Sibling, sibling_repos

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


def _siblings(result: Any, repo_root: Path) -> list[Sibling]:
    """The sibling repositories, found once per gate evaluation (kept on ``result``)."""
    if getattr(result, "sibling_repos", None) is None:
        result.sibling_repos = sibling_repos(repo_root)
    return result.sibling_repos


def heads_problem(recorded: dict[str, str] | None, siblings: list[Sibling]) -> str | None:
    """Why sibling HEADs a record saw no longer hold, else ``None``; a record without them is not checked."""
    if recorded is None:
        return None
    current = {s.path: s.head for s in siblings if s.head}
    moved = sorted(p for p in set(recorded) | set(current) if recorded.get(p) != current.get(p))
    dirty = [s.path for s in siblings if s.dirty]
    if moved:
        return f"sibling repositories changed since the review ({', '.join(moved)})"
    return f"sibling repositories have uncommitted changes ({', '.join(dirty)})" if dirty else None


def _refuse(result: Any, review: ReviewFile, why: str) -> bool:
    d = review.data
    result.carry_refused = [*(getattr(result, "carry_refused", None) or []),
                            f"{d['model']}'s {d['verdict']} at {str(d['commit'])[:12]} is stale: {why}"]
    result.stale.append(review)
    return False


def count_at_later_commit(result: Any, repo_root: Path, node: dict[str, Any], review: ReviewFile) -> bool:
    """False when ``review`` is stale at ``result.commit`` (appended to ``result.stale``).

    While a sibling repository exists (:mod:`specy_road.sibling_repos`) the bookkeeping carry never applies, and
    a record's ``sibling_heads`` must still be the siblings' HEADs, clean; each refusal's reason is listed in
    ``result.carry_refused`` for :func:`policy_line`.
    """
    siblings = _siblings(result, repo_root)
    if same_commit(repo_root, review.data["commit"], result.commit):
        why = heads_problem(review.data.get("sibling_heads"), siblings)
        return _refuse(result, review, why) if why else True
    if only_planning_or_review_bookkeeping_since(repo_root, node, review.data["commit"], result.commit):
        if not siblings:
            result.bookkeeping_carry = True
            return True
        return _refuse(result, review, f"sibling repositories {', '.join(s.path for s in siblings)} are present "
                                       "and nested_repos does not configure them, so changes there cannot be seen")
    result.stale.append(review)
    return False


def policy_line(gate: Any) -> str:
    """``gate.summary()`` with each counted approval as ``<model>@<commit>``, carried ones marked, and why an
    approval did not carry; the ``policy:`` line of ``handoff status`` and ``review record``."""
    line = gate.summary()
    if gate.approvals:
        head, sep, rest = line.partition(",")
        listed = ", ".join(f"{a.model}@{str(a.review.data['commit'])[:12]}" + (
            "" if (gate.commit or "").startswith(str(a.review.data["commit"])) else " carried from an older commit")
            for a in gate.approvals)
        line = f"{head} ({listed}){sep}{rest}"
    return "; ".join([line, *(getattr(gate, "carry_refused", None) or [])])
