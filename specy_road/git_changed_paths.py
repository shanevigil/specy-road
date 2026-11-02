"""The one way the toolkit lists the paths a diff touches.

``git diff --name-only`` reports a rename or a copy by its destination alone,
so ``git mv docs/x.md src/x.md`` into a touch zone looked like a change inside
the zone and nothing else: the source-side deletion escaped ``worker
reconcile``, the review packet, and the finish-time implementation check.
This module parses ``--name-status -z`` with rename and copy detection forced
on and returns **both** sides of every ``R`` / ``C`` record, so the three
callers agree on what a branch changed. :func:`branch_commit_paths` reads the
same records from ``git log`` and ``git diff``, for what a branch's own commits changed.

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


def _merge_own_paths(repo_root: Path, merge: str) -> set[str] | None:
    """Paths a merge changed itself: what it changed against its first parent, less what another
    parent brought in that the merge kept as that parent had it.

    A path counts as brought in from parent ``P`` when ``P`` changed it since its merge base with the
    first parent and the merge result matches ``P`` there. A conflict resolution, an edit folded into
    the merge, and both sides of a rename made in it still count.
    """
    parents = (git_stdout(["rev-list", "--parents", "-n", "1", merge], repo_root) or "").split()[1:]
    if len(parents) < 2:
        return None
    first = diff_paths(repo_root, parents[0], merge)
    if first is None:
        return None
    own = set(first)
    for other in parents[1:]:
        base = (git_stdout(["merge-base", parents[0], other], repo_root) or "").strip()
        brought = diff_paths(repo_root, base, other) if base else None
        kept = diff_paths(repo_root, other, merge)
        if brought is None or kept is None:
            return None
        own -= set(brought) - set(kept)
    return own


def branch_commit_paths(repo_root: Path, rev_range: str) -> set[str] | None:
    """Paths the branch's own commits in ``rev_range`` changed, or ``None`` when git cannot answer.

    ``--first-parent`` walks the branch's own line, so commits a merge brought
    in are not walked. Its ordinary commits are read as ``R``/``C``-aware
    records; each merge on that line adds only :func:`_merge_own_paths`, since
    ``git log --cc`` records carry a status per parent and no rename source.
    """
    out = git_stdout(["log", "--first-parent", "--no-merges", "--format=", "--name-status", "-z",
                      "--find-renames", "--find-copies", rev_range], repo_root)
    merges = git_stdout(["rev-list", "--first-parent", "--merges", rev_range], repo_root)
    if out is None or merges is None:
        return None
    paths = parse_name_status(out)
    for merge in merges.split():
        own = _merge_own_paths(repo_root, merge)
        if own is None:
            return None
        paths |= own
    return paths
