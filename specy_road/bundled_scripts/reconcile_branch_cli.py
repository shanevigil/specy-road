#!/usr/bin/env python3
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

import argparse
import sys
from pathlib import Path

from specy_road.cli_args import add_base_arg, add_remote_arg
from specy_road.finish_land_deterministic import codename_from_branch
from specy_road.finish_pr_merge import merge_integration_resolving_bookkeeping
from specy_road.git_subprocess import git_code, git_ok, git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


#: Pushing to a forge can be slow; a merge already committed must not be lost to a short timeout.
_PUSH_TIMEOUT = 300.0


def _err(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def _holds_claim(repo: Path, codename: str) -> bool:
    """Whether ``HEAD``'s registry still has this leaf's row (the leaf has not finished)."""
    doc = read_registry_at_ref(repo, "HEAD", 4.0) or {}
    return any(
        isinstance(e, dict) and e.get("codename") == codename for e in doc.get("entries") or []
    )


def _integration_sha_after_fetch(repo: Path) -> str | None:
    """The commit ``git fetch <remote> <ib>`` just wrote to ``FETCH_HEAD``, if readable."""
    return git_text(["rev-parse", "--verify", "FETCH_HEAD"], repo) or None


def _push(repo: Path, branch: str) -> int:
    """Push ``branch`` to its upstream; nothing when it has none."""
    remote = git_text(["config", f"branch.{branch}.remote"], repo)
    merge = git_text(["config", f"branch.{branch}.merge"], repo)
    if not remote or not merge:
        print(f"{branch} has no upstream; nothing pushed. "
              f"`git push -u <remote> {branch}` when ready.")
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
        return _err(f"{branch} has uncommitted tracked changes; "
                    "commit or discard them, then retry.")
    fetched, fetch_detail = git_ok(["fetch", "-q", remote, ib], repo)
    if not fetched:
        detail = fetch_detail or "git fetch failed"
        return _err(f"could not fetch {remote}/{ib}: {detail}")
    ref = _integration_sha_after_fetch(repo)
    if ref is None:
        return _err(f"could not read the integration tip after fetching {remote}/{ib}")
    pre = git_text(["rev-parse", "HEAD"], repo)
    problem = merge_integration_resolving_bookkeeping(
        repo, ref=ref, ib=ib, branch=branch, drop_row=not _holds_claim(repo, own))
    if problem is not None:
        return _err(f"could not merge {remote}/{ib} into {branch}: {problem}. "
                    "The merge was aborted and "
                    f"{branch} is unchanged; resolve code conflicts by hand (`git merge {ref}`).")
    if git_text(["rev-parse", "HEAD"], repo) == pre:
        print(f"[ok] {branch} already contains {remote}/{ib}; nothing to merge")
        return _push(repo, branch)
    print(f"[ok] merged {remote}/{ib} into {branch}: roadmap/registry.yaml resolved by rule, "
          "roadmap.md and roadmap-context.md regenerated")
    return _push(repo, branch)


def build_parser() -> argparse.ArgumentParser:
    """The ``specy-road reconcile-branch`` parser."""
    p = argparse.ArgumentParser(
        prog="specy-road reconcile-branch",
        description=(
            "In a leaf's worktree: fetch the integration branch and merge it into the feature "
            "branch, resolving roadmap/registry.yaml by rule and regenerating roadmap.md and "
            "roadmap-context.md; commit, and push when the branch has an upstream. Any other "
            "conflict aborts the merge and exits 1."
        ),
    )
    add_repo_root_arg(p)
    p.add_argument("node_id", nargs="?", default=None, metavar="NODE_ID",
                   help="Refuse unless HEAD is this leaf's feature branch.")
    add_base_arg(p)
    add_remote_arg(p)
    return p


def _codename(root, node_id: str | None) -> str | None:
    if node_id is None:
        return None
    from specy_road.roadmap_load import load_roadmap

    node = next((n for n in load_roadmap(root)["nodes"] if n.get("id") == node_id), None)
    if node is None or not node.get("codename"):
        raise SystemExit(f"error: no leaf {node_id!r} with a codename in the roadmap.")
    return node["codename"]


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    root = resolve_repo_root(args)
    base, remote, warns = resolve_integration_defaults(
        root, explicit_base=args.base, explicit_remote=args.remote)
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    codename = _codename(root, args.node_id)
    raise SystemExit(reconcile_branch(root, ib=base, remote=remote, codename=codename))


if __name__ == "__main__":
    main()
