#!/usr/bin/env python3
"""Report registry claims with no branch in this clone, and remove named ones.

``abort-task-pickup`` is the right tool while you still hold the branch: it
knows the node, deletes the branch and cleans ``work/``. It cannot help once
the branch is gone — it refuses to run anywhere but ``feature/rm-*`` — and the
documented fallback was to hand-edit ``roadmap/registry.yaml``, commit and push.
This command is that fallback with the git bookkeeping done for you.

**Removal is never inferred.** Pickup pushes the *registry* and then creates the
feature branch **locally**, without pushing it, so a healthy claim held by
another clone looks exactly like an orphan from here: no local branch, no remote
branch, a row on the integration branch. That is why F-014 only ever warns.
Reporting is therefore advisory, and every removal names its codename so the
operator — not this command — asserts the claim is dead.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.bundled_scripts.do_next_task_self_heal import detect_stale_claims
from specy_road.bundled_scripts.repo_ops import git_run, sync_integration_branch
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.git_subprocess import local_branch_exists
from specy_road.registry_yaml import read_registry, registry_path, write_registry
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def _report(root: Path, reg: dict, remote: str, base: str) -> int:
    """List rows whose branch this clone cannot see. Exit 1 when any exist."""
    stale = detect_stale_claims(repo_root=root, reg=reg, remote=remote)
    total = len(reg.get("entries") or [])
    if not stale:
        print(f"OK: {total} registry claim(s), every branch accounted for.")
        return 0
    print(
        f"{len(stale)} of {total} registry claim(s) have no feature branch in "
        "this clone:",
        file=sys.stderr,
    )
    for entry in stale:
        print(
            f"  {entry.get('codename', '?')}  node={entry.get('node_id', '?')}  "
            f"branch={entry.get('branch', '?')}  started={entry.get('started', '?')}",
            file=sys.stderr,
        )
    print(
        "\n  A claim held by another clone looks identical from here, because "
        "pickup\n"
        "  pushes the registry but keeps the feature branch local. Confirm the "
        "claim is\n"
        "  dead before removing it, then:\n"
        f"    specy-road registry-prune --remove <CODENAME>   # commits and "
        f"pushes {remote}/{base}\n"
        "  If you still have the branch, use abort-task-pickup from it instead.",
        file=sys.stderr,
    )
    return 1


def _resolve_removals(root: Path, reg: dict, codenames: list[str]) -> list[dict]:
    """The rows to drop, or exit with the reason a named codename cannot go."""
    by_codename = {
        e.get("codename"): e for e in reg.get("entries") or [] if isinstance(e, dict)
    }
    rows: list[dict] = []
    for codename in codenames:
        entry = by_codename.get(codename)
        if entry is None:
            print(
                f"error: no registry claim with codename {codename!r}. "
                "Run specy-road registry-prune to list what is registered.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        branch = entry.get("branch") or f"feature/rm-{codename}"
        if local_branch_exists(root, branch):
            print(
                f"error: {branch} still exists in this clone, so this claim is "
                "not an orphan.\n"
                f"  Finish it, or release it with: git checkout {branch} && "
                "specy-road abort-task-pickup",
                file=sys.stderr,
            )
            raise SystemExit(1)
        rows.append(entry)
    return rows


def _remove_and_push(
    root: Path, reg: dict, rows: list[dict], remote: str, base: str
) -> int:
    """Drop the rows, commit on the integration branch, push. Never silent."""
    codenames = [r.get("codename") for r in rows]
    reg["entries"] = [
        e for e in reg.get("entries") or [] if e.get("codename") not in set(codenames)
    ]
    write_registry(registry_path(root), reg)
    rel = str(registry_path(root).relative_to(root))
    git_run(root, "add", rel)
    summary = ", ".join(str(c) for c in codenames)
    git_run(
        root,
        "commit",
        "-m",
        f"chore(registry): prune stale claim(s) {summary}",
    )
    print(f"-> git push {remote} {base}")
    git_run(root, "push", remote, base)
    for row in rows:
        print(f"[ok] removed claim {row.get('codename')} (node {row.get('node_id')})")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="specy-road registry-prune",
        description=(
            "Report registry claims whose feature/rm-* branch is missing from "
            "this clone, and remove ones you name. Removal commits on the "
            "integration branch and pushes it."
        ),
    )
    add_repo_root_arg(p)
    p.add_argument(
        "--remove",
        action="append",
        default=[],
        metavar="CODENAME",
        dest="remove",
        help=(
            "Remove this claim (repeatable). Refuses when the feature branch "
            "still exists here — use abort-task-pickup for that."
        ),
    )
    p.add_argument(
        "--base",
        default=None,
        metavar="BRANCH",
        help="Integration branch (default: roadmap/git-workflow.yaml, else main).",
    )
    p.add_argument(
        "--remote",
        default=None,
        metavar="NAME",
        help="Git remote (default: roadmap/git-workflow.yaml, else origin).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    root = resolve_repo_root(args)
    base, remote, gw_warns = resolve_integration_defaults(
        root,
        explicit_base=args.base,
        explicit_remote=args.remote,
    )
    for w in gw_warns:
        print(f"warning: {w}", file=sys.stderr)

    if not args.remove:
        # Report against local state: read-only, and useful with no network.
        raise SystemExit(_report(root, read_registry(registry_path(root)), remote, base))

    sync_integration_branch(
        root,
        base,
        remote,
        retry_hint="retry registry-prune",
        clean_tree_detail=(
            "Removing a registry claim commits on the integration branch."
        ),
    )
    reg = read_registry(registry_path(root))
    rows = _resolve_removals(root, reg, args.remove)
    raise SystemExit(_remove_and_push(root, reg, rows, remote, base))


if __name__ == "__main__":
    main()
