#!/usr/bin/env python3
"""Mark implementation as human-reviewed (registry) after reading work/implementation-summary."""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

import yaml
from specy_road.git_workflow_config import require_implementation_review_before_finish
from specy_road.feature_rm_registry import resolve_feature_rm_registry_context
from specy_road.registry_yaml import registry_path, write_registry
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.bundled_scripts.work_dir_stash import (
    restore_work_dir_changes as _restore_work,
    stash_work_dir_changes as _stash_work,
)
from specy_road.bundled_scripts.repo_ops import current_branch, git_run, working_tree_clean

#: Rebound by :func:`main` before any helper runs; this is only a placeholder
#: so the name exists at import. Resolving the real root here would make
#: importing the module shell out to git.
ROOT = Path.cwd()


def _save_registry(doc: dict) -> None:
    write_registry(registry_path(ROOT), doc)


def _stash_work_dir_changes() -> bool:
    return _stash_work(ROOT, "mark-implementation-reviewed")


def _restore_work_dir_changes(stashed: bool) -> None:
    _restore_work(ROOT, stashed)


def _summary_path(node_id: str) -> Path:
    return ROOT / "work" / f"implementation-summary-{node_id}.md"


def _extract_walkthrough(text: str) -> str | None:
    """Return body under a Markdown 'Walkthrough' heading, if present."""
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^#{1,2}\s+walkthrough\s*$", stripped, re.IGNORECASE):
            start = i + 1
            break
    if start is None:
        return None
    out: list[str] = []
    for line in lines[start:]:
        if re.match(r"^#{1,2}\s+\S", line) and not re.match(
            r"^#{1,2}\s+walkthrough\s*$", line.strip(), re.IGNORECASE
        ):
            break
        out.append(line)
    body = "\n".join(out).strip()
    return body or None


def _run_interactive_menu(
    *,
    summary_text: str,
    walkthrough: str | None,
) -> bool:
    """Return True if user approves."""
    print()
    print("-" * 60)
    print("[w] Show Walkthrough section only")
    print("[a] Approve — write registry (implementation reviewed)")
    print("[q] Quit without approving")
    print("-" * 60)
    while True:
        try:
            ch = input("Choice [w/a/q]: ").strip().lower()
        except EOFError:
            print("", file=sys.stderr)
            return False
        if ch == "q":
            return False
        if ch == "a":
            return True
        if ch == "w":
            if walkthrough:
                print()
                print(walkthrough)
                print()
            else:
                print(
                    "(No ## Walkthrough section in the summary file.)",
                    file=sys.stderr,
                )
            continue
        print("  Enter w, a, or q.", file=sys.stderr)


def _load_summary_text(
    args: argparse.Namespace,
    spath: Path,
) -> str:
    if spath.is_file():
        return spath.read_text(encoding="utf-8")
    if args.allow_missing_summary:
        print(
            f"warning: missing {spath.relative_to(ROOT)} — proceeding due to "
            "--allow-missing-summary.",
            file=sys.stderr,
        )
        return ""
    print(
        f"error: implementation summary not found: {spath}",
        file=sys.stderr,
    )
    print(
        "  Create this file (see docs/dev-workflow.md) or use "
        "--allow-missing-summary for emergencies.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _user_approves(
    args: argparse.Namespace,
    *,
    summary_text: str,
    walkthrough: str | None,
) -> bool:
    if sys.stdin.isatty() and not args.yes:
        return _run_interactive_menu(
            summary_text=summary_text,
            walkthrough=walkthrough,
        )
    if args.yes:
        return True
    print(
        "error: not a TTY — pass --yes to approve without the interactive menu.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _commit_registry_approved(codename: str, reg: dict) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    for e in reg.get("entries", []):
        if e.get("codename") == codename:
            e["implementation_review"] = "approved"
            e["implementation_review_at"] = now
            break
    _save_registry(reg)
    print(f"[ok] registry: implementation_review -> approved ({now})\n")

    git_run(ROOT, "add", str(registry_path(ROOT).relative_to(ROOT)))
    git_run(ROOT, 
        "commit",
        "-m",
        f"chore(rm-{codename}): mark implementation reviewed",
    )
    print("[ok] committed registry update")
    print()
    print("Next: specy-road finish-this-task")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Record human implementation review in roadmap/registry.yaml "
            "(after reading work/implementation-summary-<NODE_ID>.md)."
        ),
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Approve without interactive menu (non-TTY or automation).",
    )
    p.add_argument(
        "--allow-missing-summary",
        action="store_true",
        help="Allow approving when the implementation summary file is missing (loud warning).",
    )
    add_repo_root_arg(p)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    global ROOT
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    ROOT = resolve_repo_root(args)

    if not require_implementation_review_before_finish(ROOT):
        print(
            "require_implementation_review_before_finish is not enabled in "
            "roadmap/git-workflow.yaml — nothing to do.",
            file=sys.stderr,
        )
        print(
            "When disabled, use specy-road finish-this-task directly after implementation.",
        )
        raise SystemExit(0)

    branch = current_branch(ROOT)
    if not branch.startswith("feature/rm-"):
        print(
            f"error: current branch '{branch}' is not a roadmap feature branch "
            "(expected feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    codename, reg, entry, _nodes = resolve_feature_rm_registry_context(ROOT, branch)
    node_id = entry["node_id"]

    spath = _summary_path(node_id)
    summary_text = _load_summary_text(args, spath)

    print(f"Implementation review — [{node_id}]")
    print(f"Summary file: {spath.relative_to(ROOT)}\n")
    if summary_text:
        print(summary_text)
        print()

    walkthrough = _extract_walkthrough(summary_text) if summary_text else None

    approve = _user_approves(
        args,
        summary_text=summary_text,
        walkthrough=walkthrough,
    )

    if not approve:
        print("Aborted (registry unchanged).")
        raise SystemExit(0)

    # F-011: stash any work/ changes so the registry commit is clean,
    # then restore on top of the feature branch (where they belong).
    stashed = _stash_work_dir_changes()
    try:
        if not working_tree_clean(ROOT):
            print(
                "error: working tree is not clean (commit, stash, or "
                "discard changes outside work/ first).",
                file=sys.stderr,
            )
            raise SystemExit(1)
        _commit_registry_approved(codename, reg)
    finally:
        _restore_work_dir_changes(stashed)


if __name__ == "__main__":
    main()
