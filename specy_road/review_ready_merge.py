"""``specy-road ready`` with the trial merge ``handoff status`` makes, so a conflict shows before the hand-off."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from specy_road.review_gate_ready import add_ready_parser as _add_ready_parser, cmd_ready as _cmd_ready, trial_merge
from specy_road.review_target import ReviewTargetError, resolve_target
from specy_road.runtime_paths import resolve_repo_root


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


def cmd_ready(ns: argparse.Namespace) -> int:
    code = _cmd_ready(ns)
    if code == 0:
        for line in trial_merge_warning(resolve_repo_root(ns), ns.node_id):
            print(line, file=sys.stderr)
    return code


def add_ready_parser(sub: argparse._SubParsersAction) -> None:
    _add_ready_parser(sub)
    sub.choices["ready"].set_defaults(func=cmd_ready)
