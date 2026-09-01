"""Keep the duplicated corpus out of an agentic IDE's index.

A long-running specy-road project accumulates far more text than its roadmap
describes, and most of it is duplicated: a brief inlines its ancestor planning
sheets and its cited contracts verbatim, and a pr-body re-inlines the whole
brief. On a real 48-node repo that is ~458 KB of ``work/`` alone, roughly 70%
of it a copy of something already indexed from its primary source. An IDE index
built over that returns the same passage from a dozen near-identical files.

The fix is a substitution, not a deletion: drop the duplicated and archived
material from the index, and add ``roadmap-context.md`` — the generated digest —
which is a few kilobytes and always current. Anything dropped stays reachable
through ``specy-road search``.

**``.cursorindexingignore``, deliberately, not ``.cursorignore``.** The former
excludes files from Cursor's index and search while leaving them readable when
explicitly referenced; the latter blocks reading too, which would break every
path that search returns. Claude Code has no equivalent — it builds no semantic
index, and its ``permissions.deny`` read rules would have the same
pointer-breaking problem — so it is steered by ``CLAUDE.md`` guidance instead.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.managed_block import UNCHANGED, apply_managed_block

CURSOR_INDEXING_IGNORE = ".cursorindexingignore"
GITIGNORE = ".gitignore"

# Only tracked-but-noisy paths need listing: Cursor already skips whatever
# .gitignore covers, so work/pr-body-*.md and .specyrd/cache/ need no entry.
INDEXING_IGNORE_LINES = [
    "roadmap/archive/",
    "work/brief-*.md",
    "roadmap.md",
]

_INDEXING_NOTE = (
    "Excluded from IDE indexing, not from reading. These are either archived or\n"
    "near-verbatim duplicates of content indexed from its primary source, and\n"
    "they crowd out current decisions in search results.\n"
    "\n"
    "Read roadmap-context.md for the current state, and reach anything here with:\n"
    "  specy-road search \"<query>\" --scope all\n"
    "\n"
    "Cursor honours this file; other tools ignore it harmlessly."
)

# The history and search indexes are derived and rebuilt on demand. init project
# ships this rule for new repos, but it skips files that already exist, so a repo
# scaffolded before these caches existed would show them as untracked forever.
GITIGNORE_LINES = [".specyrd/cache/"]

_GITIGNORE_NOTE = (
    "Derived caches for `specy-road history` and `specy-road search`.\n"
    "Rebuilt from git and the working tree on demand, so never committed.\n"
    "`.specyrd/manifest.json` stays tracked."
)


def _prefixed(lines: list[str], prefix: str) -> list[str]:
    """Re-base project-relative entries onto the git root.

    Both ignore files live at the **git** root, but every entry above names a
    path inside the **project** root. Those coincide only in the embedded
    layout. Under a nested one — the project at ``sr/`` — an unprefixed
    ``roadmap/archive/`` matches nothing, and archived material silently stays
    in the IDE index: the bug this function exists to close.
    """
    if not prefix:
        return list(lines)
    return [prefix + line for line in lines]


def apply_agent_ignores(
    git_root: Path, project_prefix: str = ""
) -> dict[str, str]:
    """Write both managed blocks at the git root. Returns ``{filename: outcome}``.

    ``project_prefix`` is the project root's path within the checkout (``"sr/"``
    or ``""``), as returned by ``runtime_paths.project_prefix``.

    Both files belong to the consumer, so only the marked block is ever
    rewritten. Re-running is a no-op.
    """
    return {
        CURSOR_INDEXING_IGNORE: apply_managed_block(
            git_root / CURSOR_INDEXING_IGNORE,
            _prefixed(INDEXING_IGNORE_LINES, project_prefix),
            note=_INDEXING_NOTE,
        ),
        GITIGNORE: apply_managed_block(
            git_root / GITIGNORE,
            _prefixed(GITIGNORE_LINES, project_prefix),
            note=_GITIGNORE_NOTE,
        ),
    }


def apply_and_report(
    git_root: Path, prefix: str, written: list[str]
) -> None:
    """:func:`apply_agent_ignores`, appending a line per file actually changed.

    Lives here rather than in ``specyrd_init`` so that the reporting wording
    stays next to the thing being reported.
    """
    for name, outcome in sorted(apply_agent_ignores(git_root, prefix).items()):
        if outcome != UNCHANGED:
            written.append(f"{name} ({outcome})")
