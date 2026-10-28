"""Which git ref the review policy and roster are read from (:func:`policy_source`).

The integration branch *name* comes from ``roadmap/git-workflow.yaml`` as
committed on the remote's default branch (``refs/remotes/<remote>/HEAD``) when
that ref exists and carries the file — a ref no feature commit moves. Otherwise
it comes from the copy committed at HEAD, which a feature commit controls.
Three checks keep that from redirecting policy at a branch the feature author
made:

* **default-branch anchor** — the name above, when the anchor exists;
* **self-consistency** — the branch the name points at must itself name that
  branch as the integration branch in its own committed ``git-workflow.yaml``;
* **remote preference** — when the configured remote exists, policy is read
  from ``refs/remotes/<remote>/<name>`` and nothing else, so retargeting needs
  push rights to a branch the remote protects. Without a remote (a local-only
  repo, no remote at all) the local branch is all there is; a remote name that
  is not configured in a repo that has remotes is an error, not a local repo.

Any failure is an error the caller fails closed on, never a fall back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from specy_road.finish_implementation_check import base_ref
from specy_road.git_subprocess import git_stdout, git_text
from specy_road.review_target import full_sha

WORKFLOW_REL = "roadmap/git-workflow.yaml"


def committed_yaml(repo_root: Path, rev: str, rel: str) -> dict[str, Any]:
    text = git_stdout(["show", f"{rev}:{rel}"], repo_root)
    try:
        data = yaml.safe_load(text) if text else None
    except (yaml.YAMLError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def integration_name(repo_root: Path) -> tuple[str, str, str]:
    """``(remote, branch, where)``: the integration branch to read policy from, and whose config named it.

    The remote's default branch wins over HEAD, so a feature branch cannot nominate itself.
    """
    head = committed_yaml(repo_root, "HEAD", WORKFLOW_REL)
    remote = str(head.get("remote") or "origin")
    anchor = f"refs/remotes/{remote}/HEAD"
    pinned = committed_yaml(repo_root, anchor, WORKFLOW_REL)
    ib = str((pinned or head).get("integration_branch") or "main")
    return remote, ib, f"(roadmap/git-workflow.yaml at {anchor if pinned else 'HEAD'})"


def trusted_integration_ref(repo_root: Path, remote: str, ib: str, where: str) -> tuple[str | None, str | None]:
    """``(ref, error)`` for integration branch ``ib`` named by the workflow config ``where``."""
    remotes = (git_text(["remote"], repo_root) or "").split()
    if remotes and remote not in remotes:
        return None, (
            f"remote {remote!r} {where} is not configured, but this repo has remote(s) "
            f"{', '.join(remotes)}; review policy is read only from a configured remote's tracking ref, "
            "so fix remote on the integration branch"
        )
    if remotes:
        ref = f"refs/remotes/{remote}/{ib}"
        if not git_text(["rev-parse", "--verify", "--quiet", ref], repo_root):
            return None, (
                f"integration branch {ib!r} {where} is not fetched as {remote}/{ib}, and with the remote "
                f"{remote!r} configured the review policy is read only from that remote-tracking ref; "
                f"run `git fetch {remote} {ib}`, or fix integration_branch on the integration branch"
            )
    else:
        ref = base_ref(repo_root, remote, ib)
        if ref is None:
            return None, (
                f"integration branch {ib!r} {where} has neither {remote}/{ib} nor a local branch, "
                "so review policy cannot be read from it; fetch it, or fix integration_branch on the "
                "integration branch"
            )
    named = str(committed_yaml(repo_root, ref, WORKFLOW_REL).get("integration_branch") or "main")
    if named != ib:
        return None, (
            f"integration branch {ib!r} {where}, but {ref} names {named!r} "
            "in its own committed copy; review policy is read only from a branch that names itself. "
            f"Either HEAD was pointed at the wrong branch (fix integration_branch on this branch to {named!r}) "
            f"or {ib!r} is not the integration branch"
        )
    return ref, None


def policy_source(repo_root: Path) -> tuple[str | None, str | None]:
    """``(ref, error)``: the integration branch ref that review policy is read from.

    The remote comes from ``roadmap/git-workflow.yaml`` **as committed at
    HEAD**, and the branch name from the copy committed on the remote's default
    branch (``refs/remotes/<remote>/HEAD``) when there is one, else from HEAD's —
    never from the working tree or the ``SPECY_ROAD_INTEGRATION_BRANCH`` /
    ``SPECY_ROAD_REMOTE`` variables, which an agent can change without a trace.
    When that branch cannot be found the result is an error, not a fall back to
    the working tree: the gate fails closed. ``(None, None)`` only outside git,
    where the working tree is all there is.

    HEAD's copy is a trust anchor a feature commit can rewrite, so the branch
    named must name itself too, and with a remote configured only the
    remote-tracking ref is read (:func:`trusted_integration_ref`).
    """
    if not full_sha(repo_root, "HEAD"):
        return None, None
    return trusted_integration_ref(repo_root, *integration_name(repo_root))
