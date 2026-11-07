"""Which git ref the review policy and roster are read from (:func:`policy_source`).

In a repo with remotes, the integration branch *name* comes from
``roadmap/git-workflow.yaml`` as committed on the remote's default branch
(``refs/remotes/<remote>/HEAD``) — a ref no feature commit moves. That ref must
exist (``git clone`` sets it; ``git remote set-head <remote> <name>`` restores
it, while ``--auto`` fails when the remote's HEAD is unborn), and its copy must
name the same remote as HEAD's copy, so a feature commit cannot switch to a
secondary remote. Out of scope: a remote whose default branch the feature author
can push to. Without a remote (a local-only repo) HEAD's copy names the branch. Then:

* **self-consistency** — the branch the name points at must itself name that
  branch as the integration branch in its own committed ``git-workflow.yaml``;
* **remote preference** — with remotes, policy is read from
  ``refs/remotes/<remote>/<name>`` and nothing else, so retargeting needs push
  rights to a branch the remote protects; without, the local branch is all
  there is. A remote name that is not configured in a repo that has remotes is
  an error, not a local repo.

Any failure is an error the caller fails closed on, never a fall back. The
missing-ref error may name a branch in ``git remote set-head``. That sentence is
for the developer (one ``git show`` per remote-tracking ref, and only on that
path); the gate does not read policy from it.
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
    text = git_stdout(["show", f"{rev}:./{rel}"], repo_root)   # ./ = relative to the project root, not the git root
    try:
        data = yaml.safe_load(text) if text else None
    # the tuple is review_policy_pin.UNREADABLE (M21.30): an unreadable file is never a traceback
    except (OSError, ValueError, TypeError, AttributeError, RecursionError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _hint_branch(repo_root: Path, remote: str) -> str | None:
    """The one remote branch to name in the set-head hint, or ``None`` to name none.

    Counts a ref only when its tip is not HEAD's commit and its committed workflow
    is a readable mapping whose ``integration_branch`` equals that ref's own name.
    An empty or missing value does not count as ``main``. A malformed or non-mapping
    file, or a failed ref listing, is not a match and raises nothing.
    """
    head = git_text(["rev-parse", "HEAD"], repo_root)
    listed = git_stdout(
        ["for-each-ref", "--format=%(objectname) %(refname)", f"refs/remotes/{remote}/"],
        repo_root,
    )
    if not head or listed is None:
        return None
    prefix = f"refs/remotes/{remote}/"
    found: list[str] = []
    for line in listed.splitlines():
        sha, sep, ref = line.partition(" ")
        if not sep or sha == head or not ref.startswith(prefix):
            continue
        branch = ref[len(prefix):]
        if not branch or branch == "HEAD":
            continue
        named = committed_yaml(repo_root, ref, WORKFLOW_REL).get("integration_branch")
        if isinstance(named, str) and named == branch:
            found.append(branch)
    return found[0] if len(found) == 1 else None


def _missing_anchor_message(repo_root: Path, remote: str, anchor: str) -> str:
    """Fail-closed text: a working ``set-head`` command, and why ``--auto`` does not."""
    branch = _hint_branch(repo_root, remote)
    name = branch if branch else "<name>"
    which = "" if branch else " with the remote's real default branch"
    return (
        f"{anchor} (the remote's default branch) is missing, and with a remote configured the "
        f"integration branch is named only there; run `git remote set-head {remote} {name}`{which} "
        f"(`git remote set-head {remote} --auto` fails when the remote's HEAD is unborn)"
    )


def integration_name(repo_root: Path, remotes: list[str]) -> tuple[tuple[str, str, str] | None, str | None]:
    """``((remote, branch, where), error)``: the integration branch to read policy from, and whose config named it.

    With remotes, the remote's default branch names it, so a feature branch cannot nominate itself.
    A missing ``refs/remotes/<remote>/HEAD`` stays an error. Any branch in that message is a hint, not a result.
    """
    head = committed_yaml(repo_root, "HEAD", WORKFLOW_REL)
    remote = str(head.get("remote") or "origin")
    if not remotes:
        return (remote, str(head.get("integration_branch") or "main"), "(roadmap/git-workflow.yaml at HEAD)"), None
    if remote not in remotes:
        return None, (
            f"remote {remote!r} (roadmap/git-workflow.yaml at HEAD) is not configured, but this repo has "
            f"remote(s) {', '.join(remotes)}; review policy is read only from a configured remote's "
            "tracking ref, so fix remote on the integration branch"
        )
    anchor = f"refs/remotes/{remote}/HEAD"
    if not git_text(["rev-parse", "--verify", "--quiet", f"{anchor}^{{commit}}"], repo_root):
        return None, _missing_anchor_message(repo_root, remote, anchor)
    pinned = committed_yaml(repo_root, anchor, WORKFLOW_REL)
    named = str(pinned.get("remote") or "origin")
    if named != remote:
        return None, (
            f"roadmap/git-workflow.yaml at HEAD names remote {remote!r}, but at {anchor} it names "
            f"{named!r}; review policy is read only through the remote the default branch names, "
            "so fix remote on this branch"
        )
    return (remote, str(pinned.get("integration_branch") or "main"), f"(roadmap/git-workflow.yaml at {anchor})"), None


def trusted_integration_ref(
    repo_root: Path, remotes: list[str], remote: str, ib: str, where: str
) -> tuple[str | None, str | None]:
    """``(ref, error)`` for integration branch ``ib`` named by the workflow config ``where``."""
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

    The remote and branch come from ``roadmap/git-workflow.yaml`` as committed
    on the remote's default branch, or at HEAD in a repo without remotes
    (:func:`integration_name`) — never from the working tree or the
    ``SPECY_ROAD_INTEGRATION_BRANCH`` / ``SPECY_ROAD_REMOTE`` variables, which an
    agent can change without a trace. When that branch cannot be found the
    result is an error, not a fall back: the gate fails closed. ``(None, None)``
    only outside git, where the working tree is all there is.

    The branch named must name itself too, and with a remote configured only
    the remote-tracking ref is read (:func:`trusted_integration_ref`).
    """
    if not full_sha(repo_root, "HEAD"):
        return None, None
    remotes = (git_text(["remote"], repo_root) or "").split()
    named, err = integration_name(repo_root, remotes)
    if named is None:
        return None, err
    return trusted_integration_ref(repo_root, remotes, *named)
