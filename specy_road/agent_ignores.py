"""Keep the duplicated corpus out of an agentic IDE's index.

A long-running specy-road project accumulates far more text than its roadmap
describes, and most of it is duplicated: a brief inlines its ancestor planning
sheets and every ``shared/*.md`` verbatim, and a pr-body re-inlines the whole
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

from specy_road.managed_block import apply_managed_block

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


def apply_agent_ignores(repo_root: Path) -> dict[str, str]:
    """Write both managed blocks. Returns ``{filename: outcome}``.

    Both files belong to the consumer, so only the marked block is ever
    rewritten. Re-running is a no-op.
    """
    return {
        CURSOR_INDEXING_IGNORE: apply_managed_block(
            repo_root / CURSOR_INDEXING_IGNORE,
            INDEXING_IGNORE_LINES,
            note=_INDEXING_NOTE,
        ),
        GITIGNORE: apply_managed_block(
            repo_root / GITIGNORE, GITIGNORE_LINES, note=_GITIGNORE_NOTE
        ),
    }
