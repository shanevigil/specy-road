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

from specy_road.harness_instruction_files import LOCAL_MD
from specy_road import safe_write
from specy_road.ignore_report import MATCH_LIMIT, attempt, estimate, observe, observed, print_matches  # noqa: F401 — MATCH_LIMIT re-exported
from specy_road.managed_block import CREATED, UNCHANGED, UPDATED, apply_managed_block
from specy_road.written_entry import Written

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

# Paths the CLI writes at run time that must never be committed. init project
# ships these rules for new repos, but it skips files that already exist, so a
# repo scaffolded before a path existed got it only by hand-editing .gitignore
# (0.3 adopters had to add the work/ entries themselves). A committed review
# file moves the branch past the commit the review read.
#: The directories specy-road itself writes under work/ while it runs: review
#: hand-offs, session presence, worker records and linked worktrees. A clone
#: or worktree can hold them before any human edit, so the clean-tree checks
#: (the executor and reviewer preconditions, delegate's uncommitted-work check,
#: reconcile's breach list) leave them out, as git does once they are ignored.
RUNTIME_WORK_DIRS = ("work/reviews/", "work/.sessions/", "work/.workers/", "work/.worktrees/")

#: Session files the pickup and finish commands regenerate each cycle. These
#: lived only in the template ``.gitignore``, so a repo with its own
#: ``.gitignore`` (or a nested project, whose template copy sat where git
#: never looked for the git root's paths) never received them.
SESSION_WORK_FILES = (
    "work/.on-complete-*.yaml",
    "work/prompt-*.md",
    "work/pr-body-*.md",
    "work/.milestone-session.yaml",
)

GITIGNORE_LINES = [
    ".specyrd/cache/",
    *SESSION_WORK_FILES,
    *RUNTIME_WORK_DIRS,
    "work/chores/.garden.json",   # `chore garden`'s run record; chore records beside it are left to the project
    "work/brainstorm-*-prompt.md",
    "work/brainstorm-closed/*-prompt.md",
    "roadmap/orchestration.local.yaml",
    "roadmap/decisions.local.yaml",   # `decisions add --local`: this clone's decisions overlay (M15.22)
    LOCAL_MD,
]

_GITIGNORE_NOTE = (
    "Written by specy-road at run time, never committed: derived caches for\n"
    "`history`, `search` and `brainstorm`; pickup and finish session files (a\n"
    "PR body re-inlines the brief and summary); review records (a commit would\n"
    "move the branch past the reviewed commit); session, worker and worktree\n"
    "state; the `chore garden` run record; brainstorm prompts; per-checkout\n"
    "orchestration availability overlay; per-clone decisions overlay.\n"
    "Also never committed: .specyrd/AGENTS.local.md, your personal addendum to\n"
    "specy-road's agent rules. `.specyrd/manifest.json`, when present, stays tracked."
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


def _seed(path: Path, text: str, dry_run: bool) -> bool:
    """Start a missing ``path`` with ``text``; whether it was (or would be) new.

    Never writes through a symlink, dangling or not; the block refuses it.
    """
    if not text or path.is_file() or path.is_symlink():
        return False
    if not dry_run:
        try:
            safe_write.write(path.parent, path, text)
        except OSError:
            return False
    return True


def apply_agent_ignores(
    git_root: Path,
    project_prefix: str = "",
    *,
    dry_run: bool = False,
    gitignore_seed: str = "",
) -> dict[str, str]:
    """Write both managed blocks at the git root. Returns ``{filename: outcome}``.

    ``project_prefix`` is the project root's path within the checkout (``"sr/"``
    or ``""``), as returned by ``runtime_paths.project_prefix``.

    ``gitignore_seed`` is text a missing ``.gitignore`` starts with, above the
    block (``init project``'s commented template). The file is still reported
    as created, so a dry run, which writes no seed, reports the same outcome.

    Both files belong to the consumer, so only the marked block is ever
    rewritten. Re-running is a no-op. Both go through the safe-write rule
    (``strict``): a symlink of any kind at either name is refused, not followed.
    """
    seeded = _seed(git_root / GITIGNORE, gitignore_seed, dry_run)
    gitignore = apply_managed_block(
        git_root / GITIGNORE,
        _prefixed(GITIGNORE_LINES, project_prefix),
        note=_GITIGNORE_NOTE,
        dry_run=dry_run,
        strict=True,
    )
    return {
        CURSOR_INDEXING_IGNORE: apply_managed_block(
            git_root / CURSOR_INDEXING_IGNORE,
            _prefixed(INDEXING_IGNORE_LINES, project_prefix),
            note=_INDEXING_NOTE,
            dry_run=dry_run,
            strict=True,
        ),
        GITIGNORE: CREATED if seeded and gitignore == UPDATED else gitignore,
    }


def apply_and_report(
    git_root: Path,
    prefix: str,
    written: list[str],
    *,
    dry_run: bool = False,
    gitignore_seed: str = "",
) -> None:
    """:func:`apply_agent_ignores`, appending a line per file actually changed.

    Lives here rather than in ``specyrd_init`` so that the reporting wording
    stays next to the thing being reported. Under ``dry_run`` the outcomes are
    computed and reported without writing, so a dry run previews these blocks
    instead of omitting them.

    When ``.gitignore`` changes in a git checkout, a note lists the files the
    new rules reach (:mod:`specy_road.ignore_report`): observed by git before
    and after a real write, estimated and labelled so in a dry run. It is
    advisory: a failure prints ``ignore check skipped: <reason>`` and the
    write is the same call either way.
    """
    noted = (git_root / ".git").exists() and apply_agent_ignores(
        git_root, prefix, dry_run=True, gitignore_seed=gitignore_seed)[GITIGNORE] in (CREATED, UPDATED)
    if noted:
        before = attempt(lambda: estimate(git_root, prefix, gitignore_seed, apply_agent_ignores)
                         if dry_run else observe(git_root))
    outcomes = apply_agent_ignores(
        git_root, prefix, dry_run=dry_run, gitignore_seed=gitignore_seed
    )
    if noted and outcomes[GITIGNORE] in (CREATED, UPDATED):
        changed = before if dry_run or isinstance(before, str) else attempt(lambda: observed(git_root, before))
        print_matches(changed, estimated=dry_run)
    for name, outcome in sorted(outcomes.items()):
        if outcome != UNCHANGED:
            written.append(Written(name, outcome))
