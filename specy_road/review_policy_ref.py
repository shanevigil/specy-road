"""Which git ref the review policy and roster are read from (``review_gate.policy_source``).

The integration branch *name* comes from ``roadmap/git-workflow.yaml`` as
committed at HEAD — which a feature commit controls. Two checks keep that
from redirecting policy at a branch the feature author made:

* **self-consistency** — the branch the name points at must itself name that
  branch as the integration branch in its own committed ``git-workflow.yaml``;
* **remote preference** — when the configured remote exists, policy is read
  from ``refs/remotes/<remote>/<name>`` and nothing else, so retargeting needs
  push rights to a branch the remote protects. Without a remote (a local-only
  repo) the local branch is all there is.

Any failure is an error the caller fails closed on, never a fall back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from specy_road.finish_implementation_check import base_ref
from specy_road.git_subprocess import git_stdout, git_text

WORKFLOW_REL = "roadmap/git-workflow.yaml"


def committed_yaml(repo_root: Path, rev: str, rel: str) -> dict[str, Any]:
    text = git_stdout(["show", f"{rev}:{rel}"], repo_root)
    try:
        data = yaml.safe_load(text) if text else None
    except (yaml.YAMLError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _remote_configured(repo_root: Path, remote: str) -> bool:
    return remote in (git_text(["remote"], repo_root) or "").split()


def trusted_integration_ref(repo_root: Path, remote: str, ib: str) -> tuple[str | None, str | None]:
    """``(ref, error)`` for integration branch ``ib`` named by HEAD's workflow config."""
    where = "(roadmap/git-workflow.yaml at HEAD)"
    if _remote_configured(repo_root, remote):
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
            f"HEAD's roadmap/git-workflow.yaml names integration branch {ib!r}, but {ref} names {named!r} "
            "in its own committed copy; review policy is read only from a branch that names itself. "
            f"Either HEAD was pointed at the wrong branch (fix integration_branch on this branch to {named!r}) "
            f"or {ib!r} is not the integration branch"
        )
    return ref, None
