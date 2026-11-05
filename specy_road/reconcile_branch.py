"""``specy-road reconcile-branch``: bring a PR-mode leaf branch level with the integration branch.

Under ``on_complete: pr`` every open PR conflicts on ``roadmap/registry.yaml``
and the two generated files as soon as another leaf's PR merges, even with no
shared code. Finish resolves those paths when it opens the PR
(:func:`specy_road.finish_pr_merge.merge_integration_resolving_bookkeeping`);
this command runs the same merge later, in the leaf's worktree, then commits
and pushes. A conflict on any other path is work for a person: the merge is
aborted, the paths are named, and the branch stays where it was.

A command rather than a ``.gitattributes`` merge driver: forge merges (GitHub,
GitLab) never run custom drivers, and a driver sees one file at a time, so it
cannot render the generated files from the merged graph.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.finish_implementation_check import base_ref
from specy_road.finish_land_deterministic import codename_from_branch
from specy_road.finish_pr_merge import merge_integration_resolving_bookkeeping
from specy_road.git_subprocess import git_code, git_ok, git_text
from specy_road.registry_remote_overlay_merge import read_registry_at_ref

#: Pushing to a forge can be slow; a merge already committed must not be lost to a short timeout.
_PUSH_TIMEOUT = 300.0


def _err(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def _holds_claim(repo: Path, codename: str) -> bool:
    """Whether ``HEAD``'s registry still has this leaf's row (the leaf has not finished)."""
    doc = read_registry_at_ref(repo, "HEAD", 4.0) or {}
    return any(isinstance(e, dict) and e.get("codename") == codename for e in doc.get("entries") or [])


def _push(repo: Path, branch: str) -> int:
    """Push ``branch`` to its upstream; nothing when it has none."""
    remote = git_text(["config", f"branch.{branch}.remote"], repo)
    merge = git_text(["config", f"branch.{branch}.merge"], repo)
    if not remote or not merge:
        print(f"{branch} has no upstream; nothing pushed. `git push -u <remote> {branch}` when ready.")
        return 0
    code, out = git_code(["push", remote, f"HEAD:{merge}"], repo, timeout=_PUSH_TIMEOUT)
    if code != 0:
        return _err(f"the merge commit is on {branch}, but pushing it to {remote} failed: {out}")
    print(f"[ok] pushed {branch} to {remote}")
    return 0


def reconcile_branch(repo: Path, *, ib: str, remote: str, codename: str | None = None) -> int:
    """Merge ``remote/ib`` into the checked-out leaf branch, bookkeeping by rule. Exit code."""
    branch = git_text(["symbolic-ref", "--short", "-q", "HEAD"], repo)
    own = codename_from_branch(branch or "")
    if own is None:
        return _err(f"HEAD is {branch or 'detached'}, not a feature/rm-<codename> branch; "
                    "run reconcile-branch in the leaf's worktree.")
    if codename is not None and own != codename:
        return _err(f"HEAD is {branch}, but that leaf's branch is feature/rm-{codename}.")
    if git_text(["status", "--porcelain", "--untracked-files=no"], repo):
        return _err(f"{branch} has uncommitted tracked changes; commit or discard them, then retry.")
    git_ok(["fetch", "-q", remote, ib], repo)
    ref = base_ref(repo, remote, ib)
    if ref is None:
        return _err(f"neither {remote}/{ib} nor {ib} exists here.")
    pre = git_text(["rev-parse", "HEAD"], repo)
    problem = merge_integration_resolving_bookkeeping(
        repo, ref=ref, ib=ib, branch=branch, drop_row=not _holds_claim(repo, own))
    if problem is not None:
        return _err(f"could not merge {ref} into {branch}: {problem}. The merge was aborted and "
                    f"{branch} is unchanged; resolve code conflicts by hand (`git merge {ref}`).")
    if git_text(["rev-parse", "HEAD"], repo) == pre:
        print(f"[ok] {branch} already contains {ref}; nothing to do")
        return 0
    print(f"[ok] merged {ref} into {branch}: roadmap/registry.yaml resolved by rule, "
          "roadmap.md and roadmap-context.md regenerated")
    return _push(repo, branch)
