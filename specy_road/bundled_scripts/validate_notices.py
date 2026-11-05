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


def _trim_trailing_spaces(line: str) -> str:
    """``line`` without its trailing unescaped spaces, as git's ``trim_trailing_spaces`` reads it.

    A backslash escapes the character after it, so ``"a\\ "`` keeps its space.
    """
    end, i = None, 0
    while i < len(line):
        if line[i] == " ":
            end = i if end is None else end
        else:
            end = None
            i += line[i] == "\\"   # skip the escaped character
        i += 1
    return line if end is None else line[:end]


def _patterns(text: str) -> list[str]:
    """The ignore patterns in ``text``, each exactly as git reads it.

    Like git: lines split on ``\\n`` only, one trailing ``\\r`` dropped, a line
    starting with ``#`` is a comment, trailing unescaped spaces are trimmed, and
    nothing else changes (a leading space, ``\\#``, ``!`` and ``\\!`` all stay
    as written), so two lines compare equal only when git reads the same pattern.
    """
    lines = (ln[:-1] if ln.endswith("\r") else ln for ln in text.split("\n"))
    return [p for ln in lines if not ln.startswith("#") and (p := _trim_trailing_spaces(ln))]


def notice_repeated_ignore_patterns(root: Path) -> None:
    """One notice naming the managed ``.gitignore`` patterns the file already lists above the markers.

    Report only: the lines above the block belong to the project, so validate never edits them.
    """
    try:
        text = ((git_root(root) or root) / ".gitignore").read_bytes().decode("utf-8", errors="replace")
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
