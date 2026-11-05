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

import shutil
import subprocess
import tempfile
from pathlib import Path

from specy_road.git_subprocess import git_stdout
from specy_road.git_subprocess import run as git_run
from specy_road.harness_instruction_files import LOCAL_MD
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
    "work/brainstorm-*-prompt.md",
    "work/brainstorm-closed/*-prompt.md",
    "roadmap/orchestration.local.yaml",
    LOCAL_MD,
]

_GITIGNORE_NOTE = (
    "Written by specy-road at run time, never committed: derived caches for\n"
    "`history`, `search` and `brainstorm`; pickup and finish session files (a\n"
    "PR body re-inlines the brief and summary); review records (a commit would\n"
    "move the branch past the reviewed commit); session, worker and worktree\n"
    "state; brainstorm prompts; per-checkout orchestration availability overlay.\n"
    "Also never committed: .specyrd/AGENTS.local.md, your personal addendum to\n"
    "specy-road's agent rules. `.specyrd/manifest.json` stays tracked."
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
            path.write_text(text, encoding="utf-8")
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
    rewritten. Re-running is a no-op.
    """
    seeded = _seed(git_root / GITIGNORE, gitignore_seed, dry_run)
    gitignore = apply_managed_block(
        git_root / GITIGNORE,
        _prefixed(GITIGNORE_LINES, project_prefix),
        note=_GITIGNORE_NOTE,
        dry_run=dry_run,
    )
    return {
        CURSOR_INDEXING_IGNORE: apply_managed_block(
            git_root / CURSOR_INDEXING_IGNORE,
            _prefixed(INDEXING_IGNORE_LINES, project_prefix),
            note=_INDEXING_NOTE,
            dry_run=dry_run,
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
    """
    matches = _new_rule_matches(git_root, prefix, gitignore_seed)   # judged in a sandbox: dry and real agree
    outcomes = apply_agent_ignores(
        git_root, prefix, dry_run=dry_run, gitignore_seed=gitignore_seed
    )
    if outcomes[GITIGNORE] in (CREATED, UPDATED):
        print_new_rule_matches(matches)
    for name, outcome in sorted(outcomes.items()):
        if outcome != UNCHANGED:
            written.append(Written(name, outcome))


#: How many matching paths the new-rule notice lists before it gives a count.
MATCH_LIMIT = 20
TRACKED_NOTE = "still tracked; git keeps tracking it"
HIDDEN_NOTE = "untracked; now hidden from git status"


def _new_rule_matches(git_root: Path, prefix: str, seed: str = "") -> list[tuple[str, str, str]]:
    """``(path, rule, note)`` for files already in the tree that the updated ``.gitignore`` newly ignores.

    Git judges it, on the file the update would actually write: a throwaway
    ``git init`` directory gets a byte copy of the current ``.gitignore`` (and
    of every nested ``.gitignore``), is asked ``check-ignore --no-index`` about
    each path, then is updated by :func:`apply_agent_ignores` itself (same
    seed, same block position, same preserved text) and asked again. A path
    ignored only afterwards is listed, with the rule git names; a negation
    before or after the block keeps whatever precedence it really has.
    Tracked files stay tracked (an ignore rule never untracks); untracked ones
    git shows today are the ones newly hidden. The real file is never touched,
    so a dry run lists the same paths. Nothing outside a git checkout.
    """
    if not (git_root / ".git").exists():
        return []
    tracked = _ls_files(git_root, [])
    untracked = _ls_files(git_root, ["--others", "--exclude-standard"])
    if not (tracked or untracked):
        return []
    nested = _ls_files(git_root, ["--cached", "--others", "--exclude-standard", "--", ":(glob)**/.gitignore"])
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp)
        if not git_run(["init", "-q", str(sandbox)], sandbox).ok:
            return []
        for rel in (r for r in dict.fromkeys([GITIGNORE, *nested]) if (git_root / r).is_file()):
            (sandbox / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(git_root / rel, sandbox / rel)
        before_text = (sandbox / GITIGNORE).read_bytes() if (sandbox / GITIGNORE).is_file() else None
        before = _ignored(sandbox, tracked + untracked)
        apply_agent_ignores(sandbox, prefix, gitignore_seed=seed)
        if not (sandbox / GITIGNORE).is_file() or (sandbox / GITIGNORE).read_bytes() == before_text:
            return []
        after = _ignored(sandbox, tracked + untracked)
    return [(f, after[f], note) for paths, note in ((tracked, TRACKED_NOTE), (untracked, HIDDEN_NOTE))
            for f in paths if f in after and f not in before]


def _ls_files(git_root: Path, args: list[str]) -> list[str]:
    out = git_stdout(["ls-files", "-z", *args], git_root)
    return [f for f in (out or "").split("\0") if f]


def _ignored(sandbox: Path, paths: list[str]) -> dict[str, str]:
    """``{path: rule}`` for each path the ignore files in ``sandbox`` ignore, as git decides it."""
    try:
        r = subprocess.run(
            ["git", "check-ignore", "--no-index", "-v", "-z", "--stdin"],
            cwd=sandbox, input="\0".join(paths) + "\0", capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    fields = r.stdout.split("\0")
    return {path: rule for _source, _line, rule, path in zip(*[iter(fields)] * 4) if not rule.startswith("!")}


def print_new_rule_matches(matches: list[tuple[str, str, str]]) -> None:
    """List what the new ``.gitignore`` rules match, at most :data:`MATCH_LIMIT` then a count."""
    if not matches:
        return
    print(".gitignore: new rules match files already in the tree (nothing was untracked):")
    for path, rule, note in matches[:MATCH_LIMIT]:
        print(f"  {path} ({rule}): {note}")
    if len(matches) > MATCH_LIMIT:
        print(f"  … and {len(matches) - MATCH_LIMIT} more")
