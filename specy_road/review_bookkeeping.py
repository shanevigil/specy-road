"""Whether a later commit leaves an approval in force.

Operator decisions call :func:`only_planning_or_review_bookkeeping_since` without
``records`` and keep today's rule: this leaf's own sheet, its implementation
summary and its review files, and never a merge. Review records pass
``records=True``. That carry also accepts project-relative roadmap and planning
paths, and a two-parent merge from the integration branch whose non-bookkeeping
diff is unchanged. It refuses when this leaf's acceptance, touch zones or tier
changed, when its sheet has no tier value, or when the graph or sheet cannot be read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_code, git_stdout, git_text
from specy_road.review_files import REVIEWS_REL, ReviewFile
from specy_road.review_policy_ref import policy_source
from specy_road.review_target import full_sha
from specy_road.runtime_paths import project_prefix, rebase_to_project
from specy_road.sibling_repos import Sibling, literal_pathspec, sibling_repos

CARRY_NOTE = "; approvals still count (only roadmap, planning or review bookkeeping changed since the reviewed commit)"

# Review policy a reviewer must see. Under roadmap/, but not bookkeeping.
_POLICY = ("roadmap/orchestration.yaml", "roadmap/git-workflow.yaml")


def _leaf_files(node: dict[str, Any]) -> tuple[str, str]:
    """This leaf's implementation summary and its review directory, project-relative."""
    return (f"work/implementation-summary-{node['id']}.md", f"{REVIEWS_REL.as_posix()}/{node['id']}")


def _is_leaf_file(rel: str, node: dict[str, Any]) -> bool:
    summary, handoffs = _leaf_files(node)
    return rel == summary or rel == handoffs or rel.startswith(f"{handoffs}/")


def _carries_path(rel: str | None, node: dict[str, Any]) -> bool:
    """A project-relative path the wider carry accepts. ``None`` is outside the project."""
    if not rel or rel in _POLICY:
        return False
    if rel in ("roadmap.md", "roadmap-context.md") or rel.startswith(("roadmap/", "planning/")):
        return True
    return _is_leaf_file(rel, node)


def _narrow_since(repo_root: Path, node: dict[str, Any], approved: str, commit: str | None) -> bool:
    """Today's predicate: this leaf's sheet, summary and review files, and never a merge.

    A missing ``commit``, a range that is not ancestral, any merge, or any other path is false.
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
    for path in paths:
        rel = rebase_to_project(path, prefix)
        if rel is None or (rel != pd and not _is_leaf_file(rel, node)):
            return False
    return True


def _parents(repo_root: Path, sha: str) -> list[str] | None:
    """Parent shas of ``sha``, or ``None`` when git cannot answer."""
    text = git_text(["rev-list", "--parents", "-n", "1", sha], repo_root)
    if not text:
        return None
    parts = text.split()
    return parts[1:] if parts[0] == sha else None


def _on_integration(repo_root: Path, sha: str) -> bool:
    """Whether ``sha`` is on the integration history the review policy is read from."""
    ref, err = policy_source(repo_root)
    if err or not ref:
        return False
    return git_code(["merge-base", "--is-ancestor", sha, ref], repo_root)[0] == 0


def _diff_spec(path: str, prefix: str, node: dict[str, Any]) -> str | None:
    """A pathspec for one non-bookkeeping path, or ``None`` when the path carries."""
    rel = rebase_to_project(path, prefix)
    if _carries_path(rel, node):
        return None
    return f":(top,literal){path}" if rel is None else literal_pathspec(rel)


def _code_diff(repo_root: Path, left: str, right: str, node: dict[str, Any]) -> str | None:
    """The ``--full-index`` diff of non-bookkeeping paths, or ``None`` when git cannot answer.

    Bookkeeping paths are left out, including this leaf's summary and review files. Policy files stay in.
    Both sides of a comparison use this, so equal results are byte-identical.
    """
    paths = diff_paths(repo_root, left, right)
    if paths is None:
        return None
    prefix = project_prefix(repo_root)
    specs = sorted({spec for path in paths if (spec := _diff_spec(path, prefix, node))})
    if not specs:
        return ""
    return git_stdout(
        ["diff", "--full-index", "--no-color", "--no-ext-diff", left, right, "--", *specs], repo_root)


def _merge_keeps_code(repo_root: Path, sha: str, node: dict[str, Any]) -> bool:
    """A two-parent integration merge whose non-bookkeeping diff matches the first parent's."""
    parents = _parents(repo_root, sha)
    if not parents or len(parents) != 2:
        return False
    first, second = parents
    if not _on_integration(repo_root, second):
        return False
    base = git_text(["merge-base", first, second], repo_root)
    if not base:
        return False
    before = _code_diff(repo_root, base, first, node)
    after = _code_diff(repo_root, second, sha, node)
    return before is not None and before == after


def _ordinary_carries(repo_root: Path, parent: str, sha: str, node: dict[str, Any]) -> bool:
    paths = diff_paths(repo_root, parent, sha)
    if paths is None:
        return False
    prefix = project_prefix(repo_root)
    return all(_carries_path(rebase_to_project(path, prefix), node) for path in paths)


def _commits_carry(repo_root: Path, approved: str, commit: str, node: dict[str, Any]) -> bool:
    """Every first-parent commit in the range is bookkeeping, or a code-neutral integration merge.

    ``--first-parent`` does not walk commits the merge brought in; the diff comparison covers those.
    Any other merge shape, an unrelated merge, or a failed git query refuses the whole range.
    """
    listed = git_text(["rev-list", "--first-parent", f"{approved}..{commit}"], repo_root)
    if listed is None:
        return False
    for sha in listed.split():
        parents = _parents(repo_root, sha)
        if not parents or len(parents) > 2:
            return False
        if len(parents) == 2:
            if not _merge_keeps_code(repo_root, sha, node):
                return False
            continue
        if not _ordinary_carries(repo_root, parents[0], sha, node):
            return False
    return True


def _node_by_key(repo_root: Path, commit: str, node: dict[str, Any]) -> dict[str, Any] | None:
    """``node``'s ``node_key`` in the graph at ``commit``, across chunk moves."""
    key = node.get("node_key")
    if not isinstance(key, str) or not key:
        return None
    nodes = load_roadmap_nodes_at_ref(repo_root, commit)
    if not nodes:
        return None
    found = [item for item in nodes if item.get("node_key") == key]
    return found[0] if len(found) == 1 else None


def _sheet_text(repo_root: Path, commit: str, node: dict[str, Any]) -> str | None:
    """The sheet ``node`` names at ``commit``, or ``None`` when it cannot be read."""
    rel = str(node.get("planning_dir") or "").strip().strip("/")
    if not rel:
        return None
    return git_stdout(["show", f"{commit}:./{rel}"], repo_root)


def _contract_problem(before: dict[str, Any], after: dict[str, Any]) -> str | None:
    if before.get("acceptance") != after.get("acceptance"):
        return "this leaf's acceptance changed"
    if before.get("touch_zones") != after.get("touch_zones"):
        return "this leaf's touch zones changed"
    return None


def _tier_problem(old: str, new: str) -> str | None:
    """Why the sheet's tier refuses the carry. A sheet with no tier value is not eligible."""
    from specy_road.review_override import sheet_tier

    old_tier, new_tier = sheet_tier(old), sheet_tier(new)
    if old_tier != new_tier:
        return "this leaf's tier changed"
    if old_tier is None:
        return "this leaf's planning sheet has no tier value"
    return None


def _evidence_problem(repo_root: Path, approved: str, commit: str, node: dict[str, Any]) -> str | None:
    """Why this leaf's own contract refuses a carry the paths would allow."""
    before, after = _node_by_key(repo_root, approved, node), _node_by_key(repo_root, commit, node)
    if before is None or after is None:
        return "this leaf's graph cannot be resolved"
    if problem := _contract_problem(before, after):
        return problem
    old, new = _sheet_text(repo_root, approved, before), _sheet_text(repo_root, commit, after)
    if old is None or new is None:
        return "this leaf's planning sheet cannot be resolved"
    return _tier_problem(old, new)


def only_planning_or_review_bookkeeping_since(
    repo_root: Path, node: dict[str, Any], approved: str, commit: str | None, *, records: bool = False,
) -> bool | str:
    """Whether ``approved..commit`` keeps an approval.

    Without ``records`` (operator decisions), today's rule: a bool, false for a merge or any path
    other than this leaf's sheet, summary and review files. With ``records``, the wider carry: true
    when it holds, false when the paths or a merge do not qualify, or a reason string when this
    leaf's acceptance, zones, tier (including a sheet with no tier value), graph or sheet refuses it.
    """
    if not records:
        return _narrow_since(repo_root, node, approved, commit)
    if not commit or git_code(["merge-base", "--is-ancestor", approved, commit], repo_root)[0] != 0:
        return False
    if not _commits_carry(repo_root, approved, commit, node):
        return False
    return _evidence_problem(repo_root, approved, commit, node) or True


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


def review_commit(result: Any, repo_root: Path, review: ReviewFile) -> str | None:
    """The full sha of ``review``'s recorded commit (``None``: not a commit here), resolved once per gate
    evaluation and kept on ``result``; every comparison and display of a record's commit goes through it."""
    cache = getattr(result, "review_commits", None)
    if cache is None:
        cache = result.review_commits = {}
    if review.path not in cache:
        cache[review.path] = full_sha(repo_root, str(review.data["commit"]))
    return cache[review.path]


def _shown(result: Any, review: ReviewFile) -> str:
    """``review``'s commit as the policy line shows it: twelve characters of the resolved sha, else the record's."""
    sha = (getattr(result, "review_commits", None) or {}).get(review.path)
    return sha[:12] if sha else f"{review.data['commit']} (not a commit in this repository)"


def _refuse(result: Any, review: ReviewFile, why: str) -> bool:
    d = review.data
    result.carry_refused = [*(getattr(result, "carry_refused", None) or []),
                            f"{d['model']}'s {d['verdict']} at {_shown(result, review)} is stale: {why}"]
    result.stale.append(review)
    return False


def count_at_later_commit(result: Any, repo_root: Path, node: dict[str, Any], review: ReviewFile) -> bool:
    """False when ``review`` is stale at ``result.commit`` (appended to ``result.stale``).

    A record's ``sibling_heads`` is checked first, on every path: the current sibling map (which siblings, and
    each one's HEAD, all clean) must equal it exactly, whether or not the root commit moved; a record without
    the field is not checked. While a sibling repository exists (:mod:`specy_road.sibling_repos`) the
    bookkeeping carry never applies. Review records ask for the wider carry; a reason string from it
    is listed the same way. Each refusal's reason is listed in ``result.carry_refused`` for
    :func:`policy_line`.
    """
    siblings, sha = _siblings(result, repo_root), review_commit(result, repo_root, review)
    if sha is None:
        return _refuse(result, review, "re-review the commit under review")
    if why := heads_problem(review.data.get("sibling_heads"), siblings):
        return _refuse(result, review, why)
    if sha == result.commit:
        return True
    carried = only_planning_or_review_bookkeeping_since(repo_root, node, sha, result.commit, records=True)
    if carried is True:
        if not siblings:
            result.bookkeeping_carry = True
            return True
        return _refuse(result, review, f"sibling repositories {', '.join(s.path for s in siblings)} are present "
                                       "and nested_repos does not configure them, so changes there cannot be seen")
    if isinstance(carried, str):
        return _refuse(result, review, carried)
    result.stale.append(review)
    return False


def policy_line(gate: Any) -> str:
    """``gate.summary()`` with each counted approval as ``<model>@<commit>``, carried ones marked, and why an
    approval did not carry; the ``policy:`` line of ``handoff status`` and ``review record``."""
    line = gate.summary()
    if gate.approvals:
        head, sep, rest = line.partition(",")
        commits = getattr(gate, "review_commits", None) or {}
        listed = ", ".join(f"{a.model}@{_shown(gate, a.review)}" + (
            "" if commits.get(a.review.path) == gate.commit else " carried from an older commit")
            for a in gate.approvals)
        line = f"{head} ({listed}){sep}{rest}"
    return "; ".join([line, *(getattr(gate, "carry_refused", None) or [])])
