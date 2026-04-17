#!/usr/bin/env python3
"""Mark implementation as human-reviewed (registry) after reading work/implementation-summary."""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

import yaml
from roadmap_load import load_roadmap
from specy_road.git_workflow_config import require_implementation_review_before_finish
from specy_road.runtime_paths import default_user_repo_root
from work_dir_stash import (
    restore_work_dir_changes as _restore_work,
    stash_work_dir_changes as _stash_work,
)

ROOT = Path.cwd()
REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"


def _current_branch() -> str:
    r = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    return r.stdout.strip()


def _git(*args: str) -> None:
    subprocess.check_call(["git", *args], cwd=ROOT)


def _load_registry() -> dict:
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {"version": 1, "entries": []}


def _save_registry(doc: dict) -> None:
    with REGISTRY_PATH.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _working_tree_clean() -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return not r.stdout.strip()


def _stash_work_dir_changes() -> bool:
    return _stash_work(ROOT, "mark-implementation-reviewed")


def _restore_work_dir_changes(stashed: bool) -> None:
    _restore_work(ROOT, stashed)


def _resolve_context(branch: str) -> tuple[str, dict, dict]:
    """Return (codename, registry_doc, entry) or raise SystemExit."""
    codename = branch[len("feature/rm-"):]
    reg = _load_registry()
    entries = reg.get("entries") or []
    entry = next((e for e in entries if e.get("codename") == codename), None)
    if not entry:
        print(f"error: no registry entry for codename '{codename}'.", file=sys.stderr)
        print("  Is roadmap/registry.yaml up to date?", file=sys.stderr)
        raise SystemExit(1)
    node_id = entry["node_id"]
    nodes = load_roadmap(ROOT)["nodes"]
    if not any(n["id"] == node_id for n in nodes):
        print(f"error: node '{node_id}' not found in roadmap.", file=sys.stderr)
        raise SystemExit(1)
    reg_branch = entry.get("branch")
    if not reg_branch:
        print(
            "error: registry entry is missing 'branch' — fix roadmap/registry.yaml.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if reg_branch != branch:
        print(
            f"error: registry says branch {reg_branch!r} but HEAD is {branch!r}.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return codename, reg, entry


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

    _git("add", str(REGISTRY_PATH.relative_to(ROOT)))
    _git(
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
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    global ROOT, REGISTRY_PATH
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    ROOT = (args.repo_root or default_user_repo_root()).resolve()
    REGISTRY_PATH = ROOT / "roadmap" / "registry.yaml"

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

    branch = _current_branch()
    if not branch.startswith("feature/rm-"):
        print(
            f"error: current branch '{branch}' is not a roadmap feature branch "
            "(expected feature/rm-<codename>).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    codename, reg, entry = _resolve_context(branch)
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
        if not _working_tree_clean():
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
