"""Publish roadmap/planning/governance changes: scoped git add, commit, push for the PM GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import (
    current_branch_name,
    git_ok,
    is_git_worktree,
    run,
)

# Repo-relative paths the PM GUI is expected to edit (forward slashes).
PUBLISH_PATHSPECS: tuple[str, ...] = (
    "roadmap/",
    "planning/",
    "constitution/",
    "vision.md",
    "roadmap.md",
)

_MAX_MESSAGE_LEN = 500


def _norm_rel(path: str) -> str:
    return path.replace("\\", "/").strip()


def path_in_publish_scope(rel: str) -> bool:
    """True if ``rel`` is covered by :data:`PUBLISH_PATHSPECS`."""
    r = _norm_rel(rel)
    if not r or r.endswith("/"):
        return False
    if r in ("vision.md", "roadmap.md"):
        return True
    for prefix in ("roadmap/", "planning/", "constitution/"):
        if r.startswith(prefix):
            return True
    return False


def _git_lines(repo_root: Path, args: list[str], *, timeout: float = 60.0) -> list[str]:
    ok, out = git_ok(args, repo_root, timeout=timeout)
    if not ok:
        return []
    text = (out or "").strip()
    if not text:
        return []
    return text.splitlines()


def scope_changed_files(repo_root: Path) -> list[str]:
    """Paths with any working-tree change that fall under the publish scope."""
    staged, unstaged, untracked = _collect_changed_paths(repo_root)
    all_p = staged | unstaged | untracked
    return sorted(p for p in all_p if path_in_publish_scope(p))


def _collect_changed_paths(repo_root: Path) -> tuple[set[str], set[str], set[str]]:
    """Return (staged_paths, unstaged_tracked_paths, untracked_paths), repo-relative."""
    staged = set(_git_lines(repo_root, ["diff", "--cached", "--name-only"]))
    unstaged = set(_git_lines(repo_root, ["diff", "--name-only"]))
    untracked = set(
        _git_lines(repo_root, ["ls-files", "--others", "--exclude-standard"]),
    )
    staged = {_norm_rel(p) for p in staged if p.strip()}
    unstaged = {_norm_rel(p) for p in unstaged if p.strip()}
    untracked = {_norm_rel(p) for p in untracked if p.strip()}
    return staged, unstaged, untracked


@dataclass
class PublishStatus:
    """Serializable result for ``GET /api/publish/status``."""

    can_publish: bool
    scope_dirty: bool
    blocked: bool
    blocked_reason: str | None
    detail: str | None
    current_branch: str | None
    upstream: str | None
    scope_paths: list[str] = field(default_factory=list)
    out_of_scope_paths: list[str] = field(default_factory=list)


def _upstream_ref(repo_root: Path) -> str | None:
    ok, out = git_ok(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        repo_root,
        timeout=30.0,
    )
    if not ok or not (out or "").strip():
        return None
    return (out or "").strip()


def classify_publish_status(repo_root: Path) -> PublishStatus:
    """Inspect git state; determine if scoped publish is allowed."""
    if not is_git_worktree(repo_root):
        return PublishStatus(
            can_publish=False,
            scope_dirty=False,
            blocked=True,
            blocked_reason="not_git_repo",
            detail="This folder is not a git repository.",
            current_branch=None,
            upstream=None,
        )

    branch = current_branch_name(repo_root)
    upstream = _upstream_ref(repo_root)

    staged, unstaged, untracked = _collect_changed_paths(repo_root)

    all_changes = staged | unstaged | untracked
    in_scope = {p for p in all_changes if path_in_publish_scope(p)}
    out_scope = sorted(p for p in all_changes if not path_in_publish_scope(p))

    staged_out = sorted(p for p in staged if not path_in_publish_scope(p))
    if staged_out:
        return PublishStatus(
            can_publish=False,
            scope_dirty=bool(in_scope),
            blocked=True,
            blocked_reason="staged_out_of_scope",
            detail=(
                "Non-roadmap files are staged. Unstage them in your editor or terminal, "
                "then try again."
            ),
            current_branch=branch,
            upstream=upstream,
            scope_paths=sorted(in_scope),
            out_of_scope_paths=staged_out[:50],
        )

    if out_scope:
        return PublishStatus(
            can_publish=False,
            scope_dirty=bool(in_scope),
            blocked=True,
            blocked_reason="out_of_scope_changes",
            detail=(
                "Other files in this repository have changes. Ask a developer for help, "
                "or commit those separately before publishing roadmap changes."
            ),
            current_branch=branch,
            upstream=upstream,
            scope_paths=sorted(in_scope),
            out_of_scope_paths=out_scope[:50],
        )

    scope_dirty = bool(in_scope)
    can = scope_dirty and branch is not None
    return PublishStatus(
        can_publish=can,
        scope_dirty=scope_dirty,
        blocked=False,
        blocked_reason=None,
        detail=None,
        current_branch=branch,
        upstream=upstream,
        scope_paths=sorted(in_scope),
        out_of_scope_paths=[],
    )


def validate_commit_message(message: str) -> str:
    """Return stripped message or raise ValueError."""
    m = (message or "").strip()
    if not m:
        raise ValueError("empty_message")
    if "\n" in m or "\r" in m:
        raise ValueError("multiline_message")
    if len(m) > _MAX_MESSAGE_LEN:
        raise ValueError("message_too_long")
    return m


def _verify_staged_index_not_empty(repo_root: Path) -> None:
    d = run(["diff", "--cached", "--quiet"], repo_root, timeout=30.0)
    if d.code == 0:
        raise ValueError("No staged changes after git add.")
    if d.code != 1:
        raise RuntimeError(f"git diff --cached failed (exit {d.code}).")


def _git_commit_roadmap(repo_root: Path, msg: str) -> None:
    r = run(["commit", "-m", msg], repo_root, timeout=120.0)
    if r.ok:
        return
    err = r.message
    if "Please tell me who you are" in err or "user.name" in err:
        raise RuntimeError(
            "Git needs your name and email on this computer. "
            "A developer can run: git config user.name and git config user.email.",
        )
    raise RuntimeError(f"git commit failed (exit {r.code}): {err or 'unknown error'}")


def _raise_push_failure(
    hint: str,
    *,
    current_branch: str | None,
) -> None:
    if "no upstream" in hint.lower() or "does not have any commits" in hint.lower():
        br = current_branch or "your-branch"
        raise RuntimeError(
            f"No upstream branch configured. Run: git push -u origin {br}",
        )
    if "rejected" in hint.lower() or "non-fast-forward" in hint.lower():
        raise RuntimeError(
            "Push was rejected (remote has new commits). "
            "Pull or merge the latest changes, then try publishing again.\n\n"
            + hint[:800],
        )
    raise RuntimeError(hint[:2000])


def publish_roadmap(repo_root: Path, message: str) -> dict[str, Any]:
    """
    Stage publish-scope paths, commit, push to upstream.

    Returns a dict with ``ok``, ``commit_sha`` (short), etc., or raises ``ValueError``
    / ``RuntimeError`` with a message suitable for API ``detail``.
    """
    msg = validate_commit_message(message)

    if not is_git_worktree(repo_root):
        raise ValueError("This folder is not a git repository.")

    st = classify_publish_status(repo_root)
    if st.blocked:
        raise ValueError(st.detail or "Cannot publish.")
    if not st.scope_dirty:
        raise ValueError("No roadmap changes to publish.")
    if st.current_branch is None:
        raise ValueError(
            "Detached HEAD or no branch checked out. Check out a branch before publishing.",
        )

    # Stage only in-scope files (avoid ``git add planning/`` when that dir is missing).
    files = scope_changed_files(repo_root)
    if not files:
        raise ValueError("No roadmap changes to publish.")
    r_add = run(["add", "--", *files], repo_root, timeout=120.0)
    if not r_add.ok:
        raise RuntimeError(
            f"git add failed (exit {r_add.code}): {r_add.message or 'unknown error'}"
        )

    _verify_staged_index_not_empty(repo_root)
    _git_commit_roadmap(repo_root, msg)

    sha_lines = _git_lines(repo_root, ["rev-parse", "--short", "HEAD"])
    short_sha = sha_lines[0] if sha_lines else None

    r_push = run(["push"], repo_root, timeout=300.0)
    if not r_push.ok:
        _raise_push_failure(
            r_push.message or "git push failed.", current_branch=st.current_branch
        )

    return {
        "ok": True,
        "commit_sha": short_sha,
        "pushed": True,
        "branch": st.current_branch,
    }


def publish_status_dict(repo_root: Path) -> dict[str, Any]:
    """JSON-serializable status for the API."""
    st = classify_publish_status(repo_root)
    return {
        "can_publish": st.can_publish,
        "scope_dirty": st.scope_dirty,
        "blocked": st.blocked,
        "blocked_reason": st.blocked_reason,
        "detail": st.detail,
        "current_branch": st.current_branch,
        "upstream": st.upstream,
        "scope_paths": st.scope_paths,
        "out_of_scope_paths": st.out_of_scope_paths,
    }
