"""Non-fatal notices ``validate`` prints after the graph checks pass.

Notices go to stdout, so ``validate --strict`` does not count them as warnings.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from specy_road.context_notice_cache import fold_next_report, report_context_warnings
from specy_road.finish_ancestor_rollup import held_milestones, milestone_review_hold_notice
from specy_road.managed_block import MARKER_END, MARKER_START
from specy_road.runtime_paths import git_root


def notice_milestone_review_holds(root: Path, nodes: list[dict]) -> None:
    """One notice per milestone ``policy.milestone_full_review`` holds, with the ways out.

    Without it the only symptom of a hold was ``export --check`` / ``digest
    --check`` drift; ``upgrade`` shows these because it runs ``validate_at``.
    """
    for nid, why in held_milestones(root, nodes).items():
        print(milestone_review_hold_notice(nid, why))


__all__ = ["notice_milestone_review_holds", "notice_repeated_ignore_patterns", "parse_validate_args",
           "report_context_warnings"]


def parse_validate_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    """The ``validate`` CLI's arguments, with ``--context``; folds this run's unchanged ``context:`` warnings unless it is given.

    Lives here so the options M13.12 adds stay out of ``validate_roadmap.py``.
    """
    parser.add_argument("--context", action="store_true",
                        help="Print the context: warnings in full even when unchanged since the last validate.")
    args = parser.parse_args()
    fold_next_report(not args.context)
    return args


def _patterns(text: str) -> list[str]:
    """The ignore patterns in ``text``: stripped lines, blanks and comments left out."""
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def notice_repeated_ignore_patterns(root: Path) -> None:
    """One notice naming the managed ``.gitignore`` patterns the file already lists above the markers.

    Report only: the lines above the block belong to the project, so validate never edits them.
    """
    try:
        text = ((git_root(root) or root) / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    start = text.find(MARKER_START)
    if start < 0:
        return
    end = text.find(MARKER_END, start)
    managed = set(_patterns(text[start:end if end >= 0 else len(text)]))
    repeated = list(dict.fromkeys(p for p in _patterns(text[:start]) if p in managed))
    if repeated:
        print(f"gitignore: notice — .gitignore lists {len(repeated)} pattern(s) above the specy-road "
              f"managed block that the block repeats: {', '.join(repeated)}. They can be removed from "
              "above the markers (validate never edits the file).")
