"""Lifecycle of the ``work/`` session files that finish-this-task cleans up.

Split out of ``bundled_scripts/finish_task`` to keep that module under the
repo's per-file line cap; the ``finish_*`` modules follow the same pattern.

Tracked files get their deletion staged rather than unlinked, so the caller can
fold them into the bookkeeping commit. A bare unlink on a tracked path leaves a
dirty worktree that the next checkout silently restores.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def work_artifact_rel_paths(node_id: str) -> tuple[str, str, str]:
    """Session documents removed on finish (``pr-body-`` is excluded on purpose).

    The PR-body snapshot has to survive until ``gh pr create --body-file`` has
    run, and finish-this-task has no hook for "the PR was opened".
    """
    return (
        f"work/brief-{node_id}.md",
        f"work/prompt-{node_id}.md",
        f"work/implementation-summary-{node_id}.md",
    )


def is_git_tracked(repo_root: Path, pathspec: str) -> bool:
    """True when git tracks anything matching ``pathspec`` (git pathspec globs allowed)."""
    r = subprocess.run(
        ["git", "ls-files", "--", pathspec],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool((r.stdout or "").strip())


PR_BODY_PATHSPEC = "work/pr-body-*.md"


def warn_if_pr_body_tracked(repo_root: Path) -> None:
    """Point a repo that tracks the snapshots at the ignore rule.

    Matches the whole ``work/pr-body-*.md`` family rather than the node being
    finished: this node's snapshot was written moments ago and so is never in
    the index yet, while a project scaffolded before the ignore rule shipped is
    carrying committed snapshots from earlier tasks. Checking only the current
    node would leave exactly the repos that need this warning without one.
    """
    if not is_git_tracked(repo_root, PR_BODY_PATHSPEC):
        return
    print(
        f"[warn] git tracks {PR_BODY_PATHSPEC}. Those are regenerated snapshots "
        "of the brief plus the implementation summary, so tracking them "
        "duplicates both in history on every finish. Add "
        f"'{PR_BODY_PATHSPEC}' to .gitignore, then run "
        f"'git rm --cached {PR_BODY_PATHSPEC}' once.",
        file=sys.stderr,
    )


def remove_work_file(root_r: Path, rel: str) -> bool | None:
    """Delete ``rel`` under the repo root. True when tracked, None when absent."""
    path = (root_r / rel).resolve()
    if not path.is_file():
        return None
    try:
        path.relative_to(root_r)
    except ValueError:
        return None
    tracked = is_git_tracked(root_r, rel)
    path.unlink()
    if tracked:
        print(f"[ok] removed {rel} (tracked — staging deletion)")
    else:
        print(f"[ok] removed {rel}")
    return tracked


def cleanup_work_artifacts(repo_root: Path, node_id: str) -> list[str]:
    """Remove the node's session documents; return tracked paths to stage as deletions."""
    need_add: list[str] = []
    root_r = repo_root.resolve()
    for rel in work_artifact_rel_paths(node_id):
        if remove_work_file(root_r, rel):
            need_add.append(rel)
    return need_add


def cleanup_session_sidecar(repo_root: Path, sess_path: Path | None) -> list[str]:
    """Remove ``work/.on-complete-<NODE>.yaml``; return tracked paths to stage.

    Called from the bookkeeping phase rather than the on_complete tail so that a
    tracked copy lands in that commit. Removing it afterwards would only ever
    leave an uncommitted deletion, which the next checkout silently restores.

    The sidecar is internal handoff state rather than a document, so it goes
    regardless of ``--no-cleanup-work``.
    """
    if sess_path is None:
        return []
    root_r = repo_root.resolve()
    try:
        rel = sess_path.resolve().relative_to(root_r).as_posix()
    except ValueError:
        # A work/ symlink pointing outside the tree. Not ours to delete, and
        # raising here would abort a half-applied bookkeeping phase.
        return []
    return [rel] if remove_work_file(root_r, rel) else []
