"""The one way the toolkit lists the paths a diff touches.

``git diff --name-only`` reports a rename or a copy by its destination alone,
so ``git mv docs/x.md src/x.md`` into a touch zone looked like a change inside
the zone and nothing else: the source-side deletion escaped ``worker
reconcile``, the review packet, and the finish-time implementation check.
This module parses ``--name-status -z`` with rename and copy detection forced
on and returns **both** sides of every ``R`` / ``C`` record, so the three
callers agree on what a branch changed.

``-z`` is what makes the parse exact: a path with whitespace, a tab, or a
quote is one NUL-terminated field, never something to unquote.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.git_subprocess import git_stdout

_DIFF_ARGS = ("diff", "--name-status", "-z", "--find-renames", "--find-copies")


def parse_name_status(out: str) -> set[str]:
    """Every path in ``git diff --name-status -z`` output, both sides of ``R``/``C``."""
    fields = out.split("\0")
    paths: set[str] = set()
    i = 0
    while i < len(fields):
        status = fields[i]
        if not status:
            i += 1
            continue
        if status[0] in "RC":
            paths.update(fields[i + 1:i + 3])
            i += 3
        else:
            paths.update(fields[i + 1:i + 2])
            i += 2
    return {p for p in paths if p}


def diff_paths(repo_root: Path, *diff_args: str) -> list[str] | None:
    """Sorted paths ``git diff <diff_args>`` touches, or ``None`` when git cannot answer.

    ``diff_args`` is whatever selects the comparison — ``base...tip`` for a
    branch, ``<sha>`` for the working tree against a commit — and every
    rename or copy contributes its source as well as its destination.
    """
    out = git_stdout([*_DIFF_ARGS, *diff_args], repo_root)
    if out is None:
        return None
    return sorted(parse_name_status(out))
