#!/usr/bin/env python3
"""``specy-road branches prune``: list merged ``feature/rm-*`` branches; delete them with ``--delete``.

``finish-this-task --delete-branch`` covers the branch being finished. This is
for the backlog: PRs merged on the forge, grind sessions run without
``--delete-merged-branches``, finishes run before that flag existed.

"Merged" means the remote integration branch contains the branch, judged after
a ``git fetch --prune``. Two kinds of branch pass that test and are not done: a
claim nobody has committed to yet (its tip *is* an integration-branch commit),
and a milestone rollup branch fresh from ``start-milestone-session``. The first
still has its registry row; the second is named by an open
``milestone_execution``. Both are left alone.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.bundled_scripts.grind_session_cleanup import (
    delete_local_branch,
    delete_remote_branch,
    merged_into,
)
from specy_road.bundled_scripts.roadmap_load_at_ref import load_roadmap_nodes_at_ref
from specy_road.git_subprocess import DEFAULT_TIMEOUT, git_code, git_text
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.registry_remote_overlay_merge import read_registry_at_ref
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root

PATTERN = "feature/rm-*"


def feature_branches(root: Path, prefix: str) -> list[str]:
    out = git_text(["for-each-ref", "--format=%(refname)", prefix + PATTERN], root) or ""
    return [ref.removeprefix(prefix) for ref in out.splitlines()]


def _open_rollups(root: Path, target: str) -> set[str] | None:
    """Rollup branches ``target``'s roadmap still has open, or ``None`` if unreadable.

    The working tree can be behind the integration branch prune just fetched.
    Its roadmap would miss a rollup the remote still marks active, and a delete
    would remove it.
    """
    nodes = load_roadmap_nodes_at_ref(root, target)
    if nodes is None:
        return None
    return {
        me.get("rollup_branch")
        for node in nodes
        if isinstance(me := node.get("milestone_execution"), dict)
        and me.get("state") != "closed"
    }


def live_branches(root: Path, target: str) -> set[str] | None:
    """Branches still in use, or ``None`` when the remote roadmap cannot be read."""
    rollups = _open_rollups(root, target)
    if rollups is None:
        return None
    live: set[str] = set(rollups)
    for reg in (read_registry(registry_path(root)),
                read_registry_at_ref(root, target, DEFAULT_TIMEOUT) or {}):
        live.update(e.get("branch") for e in reg.get("entries") or [] if isinstance(e, dict))
    return live


def _merged(root: Path, prefix: str, target: str, live: set[str]) -> list[str]:
    return [
        b for b in feature_branches(root, prefix)
        if b not in live and merged_into(root, prefix + b, target)
    ]


def _delete(root: Path, local: list[str], remote_side: list[str], target: str, remote: str) -> int:
    failures = 0
    for b in local:
        failure = delete_local_branch(root, b, target)
        failures += _say(failure, f"deleted local branch {b}")
    for b in remote_side:
        failure = delete_remote_branch(root, b, target, remote)
        failures += _say(failure, f"deleted {b} on {remote}")
    return 1 if failures else 0


def _say(failure: dict | None, done: str) -> int:
    if failure is None:
        print(f"[ok] {done}")
        return 0
    print(f"[warn] {failure['branch']}: {failure['message']}", file=sys.stderr)
    return 1


def fetch_integration(root: Path, ns: argparse.Namespace) -> tuple[str, str] | None:
    """``(base, remote)`` from ``--base``/``--remote`` or config, after ``git fetch --prune``.

    ``None`` when the fetch failed, which is printed.
    """
    base, remote, warns = resolve_integration_defaults(
        root, explicit_base=ns.base, explicit_remote=ns.remote
    )
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    code, out = git_code(["fetch", "--prune", remote], root)
    if code != 0:
        print(
            f"error: git fetch --prune {remote} failed: {out}\n"
            f"  Merged means contained in {remote}/{base}, and a stale copy of "
            "it could delete work pushed since. Fix the remote, then re-run.",
            file=sys.stderr,
        )
        return None
    return base, remote


def cmd_prune(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    fetched = fetch_integration(root, ns)
    if fetched is None:
        return 1
    base, remote = fetched
    target = f"{remote}/{base}"
    live = live_branches(root, target)
    if live is None:
        print(
            f"error: could not read the roadmap at {target}. "
            "Not listing or deleting anything.",
            file=sys.stderr,
        )
        return 1
    local = _merged(root, "refs/heads/", target, live)
    remote_side = _merged(root, f"refs/remotes/{remote}/", target, live)
    if not local and not remote_side:
        print(f"Nothing to prune: no unclaimed {PATTERN} branch is merged into {target}.")
        return 0
    if ns.delete:
        return _delete(root, local, remote_side, target, remote)
    print(f"Merged into {target} and unclaimed:")
    for b in local:
        print(f"  local     {b}")
    for b in remote_side:
        print(f"  {remote:<9} {b}")
    print("Nothing deleted. Re-run with --delete to delete them.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    br = sub.add_parser("branches", help="Tidy feature/rm-* branches.")
    bsub = br.add_subparsers(dest="branches_cmd", required=True)
    prune = bsub.add_parser(
        "prune",
        description=(
            "List feature/rm-* branches, local and on the remote, that the "
            "remote integration branch already contains, after git fetch "
            "--prune. Branches with a registry claim and open milestone "
            "rollup branches are skipped. Deletes only with --delete; run it "
            "from the up-to-date integration branch, because git branch -d "
            "also wants HEAD (or the branch's upstream) to contain the branch."
        ),
    )
    prune.add_argument("--delete", action="store_true",
                       help="Delete the listed branches locally and on the remote.")
    prune.add_argument("--base", default=None, metavar="BRANCH",
                       help="Integration branch (default: roadmap/git-workflow.yaml, else main).")
    prune.add_argument("--remote", default=None, metavar="NAME",
                       help="Git remote (default: roadmap/git-workflow.yaml, else origin).")
    add_repo_root_arg(prune)
    prune.set_defaults(func=cmd_prune)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
