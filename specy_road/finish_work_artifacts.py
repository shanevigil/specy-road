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


def is_git_tracked(repo_root: Path, rel: str) -> bool:
    r = subprocess.run(
        ["git", "ls-files", "--", rel],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool((r.stdout or "").strip())


def warn_if_pr_body_tracked(repo_root: Path, rel: str) -> None:
    """Point a repo that tracks the snapshot at the ignore rule.

    Projects scaffolded before ``work/pr-body-*.md`` was added to the template
    ``.gitignore`` commit a fresh copy of the brief plus the implementation
    summary on every finish.
    """
    if not is_git_tracked(repo_root, rel):
        return
    print(
        f"[warn] {rel} is tracked in git. It is a regenerated snapshot of the "
        "brief plus the implementation summary, so tracking it duplicates both "
        "in history. Add 'work/pr-body-*.md' to .gitignore, then run "
        f"'git rm --cached {rel}' once.",
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
