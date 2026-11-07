"""``specy-road ready`` with the trial merge ``handoff status`` makes, and a CHANGELOG reminder after a successful write."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.bundled_scripts.planning_artifacts import resolve_planning_path
from specy_road.changelog_check import missing_entry_warning
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import run
from specy_road.review_gate_ready import add_ready_parser as _add_ready_parser, cmd_ready as _cmd_ready, trial_merge
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.runtime_paths import project_prefix, resolve_repo_root


def trial_merge_warning(root: Path, node_id: str) -> list[str]:
    """Lines warning that ``HEAD`` no longer merges cleanly with the integration branch; empty when it does."""
    try:
        t = resolve_target(root, node_id, "HEAD")
    except ReviewTargetError:
        return []
    tm = trial_merge(root, t.ref, t.base_ref)   # the same call handoff status makes
    if tm is None or not tm.conflicts:
        return []
    if tm.problem() is None:
        return [f"note: a trial merge with {tm.base_ref} conflicts on bookkeeping only "
                f"({', '.join(tm.conflicts)}), which does not block review"]
    return [f"warning: {tm.problem()}.",
            f"  Before handing off: run `git merge {tm.base_ref}`, resolve, commit, run the verifiers again, "
            f"and rerun `specy-road ready`; a reviewer cannot pass this commit."]


def _changelog_at(root: Path, rev: str) -> str | None:
    """``CHANGELOG.md`` at ``rev``; ``""`` when that path is absent; None when the read failed."""
    result = run(["show", f"{rev}:CHANGELOG.md"], root)
    if result.ok:
        return result.out
    if result.failure:
        return None
    msg = result.message
    quoted = f"'{rev}'"
    absent = quoted in msg and ("does not exist in " in msg or "not in " in msg)
    return "" if absent else None


def _exempt_text(root: Path, node: dict) -> str | None:
    """Acceptance lines plus the planning sheet, or None when the sheet cannot be read."""
    acceptance = node.get("acceptance") or []
    parts = [str(item) for item in acceptance] if isinstance(acceptance, list) else []
    rel = node.get("planning_dir")
    if not isinstance(rel, str) or not rel.strip():
        return "\n".join(parts)
    try:
        path = resolve_planning_path(root, rel)
        parts.append(path.read_text(encoding="utf-8") if path.is_file() else "")
    except (OSError, ValueError):
        return None
    return "\n".join(parts)


def _changelog_warning(root: Path, node_id: str) -> str | None:
    """The reminder for a successful ready, or None when git or a read cannot answer."""
    try:
        target = resolve_target(root, node_id, "HEAD")
    except ReviewTargetError:
        return None
    if not target.base or not target.commit:
        return None
    changed = diff_paths(root, f"{target.base}...{target.commit}")
    if changed is None:
        return None
    head = _changelog_at(root, target.commit)
    base = _changelog_at(root, target.base)
    if head is None or base is None:
        return None
    exempt = _exempt_text(root, target.node)
    if exempt is None:
        return None
    return missing_entry_warning(changed, project_prefix(root), base, head, exempt)


def cmd_ready(ns: argparse.Namespace) -> int:
    code = _cmd_ready(ns)
    if code == 0:
        root = resolve_repo_root(ns)
        for line in trial_merge_warning(root, ns.node_id):
            print(line, file=sys.stderr)
        reminder = _changelog_warning(root, ns.node_id)
        if reminder:
            print(reminder, file=sys.stderr)
    return code


def add_ready_parser(sub: argparse._SubParsersAction) -> None:
    _add_ready_parser(sub)
    sub.choices["ready"].set_defaults(func=cmd_ready)
