"""Best-effort git provenance for an archived subtree.

Answers "what was this work delivered on?" by reading ``milestone_execution``
off the archived root node and resolving what git still knows: the rollup tip,
the merge commit that carried it into the integration branch, and the nearest
tag reachable from there.

Every lookup is best-effort and returns ``None`` rather than raising. A repo
with no rollup history, deleted branches, or no tags at all still archives
cleanly — it simply records less. Nothing here creates git objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_text


def resolve_ref(repo: Path, branch: str | None, remote: str | None = None) -> str | None:
    """SHA for ``branch``, trying the local ref then ``<remote>/<branch>``.

    Rollup branches are routinely deleted locally once merged, so the remote
    ref is often the only one left.
    """
    if not branch:
        return None
    candidates = [branch, f"refs/heads/{branch}"]
    if remote:
        candidates.append(f"{remote}/{branch}")
        candidates.append(f"refs/remotes/{remote}/{branch}")
    for ref in candidates:
        sha = git_text(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], repo)
        if sha:
            return sha
    return None


def merge_commit_for(repo: Path, rollup_tip: str, integration_sha: str) -> str | None:
    """The merge that first brought ``rollup_tip`` into the integration branch.

    ``--ancestry-path`` restricts the walk to commits that actually descend from
    the rollup tip, so unrelated merges on the integration branch are excluded.
    ``rev-list`` emits newest-first, so the **last** line is the earliest such
    merge — the one that landed the work.
    """
    out = git_text(
        [
            "rev-list",
            "--ancestry-path",
            "--merges",
            f"{rollup_tip}..{integration_sha}",
        ],
        repo,
    )
    if not out:
        return None
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return lines[-1] if lines else None


def nearest_tag(repo: Path, ref: str | None) -> str | None:
    """Closest tag reachable from ``ref`` (``git describe --tags --abbrev=0``)."""
    if not ref:
        return None
    return git_text(["describe", "--tags", "--abbrev=0", ref], repo) or None


def capture_provenance(root: Path, root_node: dict[str, Any]) -> dict[str, Any]:
    """Provenance block for the archive record, from ``milestone_execution`` + git.

    Returns a dict with every key present (``None`` where unknown) so the record
    shape stays stable and readers never have to distinguish "absent" from
    "unresolvable".
    """
    me = root_node.get("milestone_execution")
    me = me if isinstance(me, dict) else {}
    rollup_branch = me.get("rollup_branch")
    integration_branch = me.get("integration_branch")
    remote = me.get("remote")
    closed_at = me.get("closed_at")

    rollup_tip = resolve_ref(root, rollup_branch, remote)
    integration_sha = resolve_ref(root, integration_branch, remote)
    merge_commit = (
        merge_commit_for(root, rollup_tip, integration_sha)
        if rollup_tip and integration_sha
        else None
    )
    return {
        "rollup_branch": rollup_branch if isinstance(rollup_branch, str) else None,
        "integration_branch": (
            integration_branch if isinstance(integration_branch, str) else None
        ),
        "rollup_tip": rollup_tip,
        "merge_commit": merge_commit,
        "nearest_tag": nearest_tag(root, merge_commit or rollup_tip),
        "closed_at": closed_at if isinstance(closed_at, str) else None,
    }
