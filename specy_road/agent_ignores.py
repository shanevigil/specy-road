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

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

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

    The note on files the new ``.gitignore`` rules match is advisory: it is
    worked out first, only when ``.gitignore`` will change, and any failure
    while working it out prints one ``ignore check skipped: <reason>`` line in
    place of the note. It never stops or alters the writes below.
    """
    note: list[tuple[str, str, str]] | str = []
    if apply_agent_ignores(git_root, prefix, dry_run=True, gitignore_seed=gitignore_seed)[GITIGNORE] in (
            CREATED, UPDATED):
        try:
            note = _new_rule_matches(git_root, prefix, gitignore_seed)
        except (OSError, ValueError, subprocess.SubprocessError, IgnoreCheckSkipped) as e:
            note = str(e) or type(e).__name__
    outcomes = apply_agent_ignores(
        git_root, prefix, dry_run=dry_run, gitignore_seed=gitignore_seed
    )
    if outcomes[GITIGNORE] in (CREATED, UPDATED):
        if isinstance(note, str):
            print(f"ignore check skipped: {note}")
        else:
            print_new_rule_matches(note)
    for name, outcome in sorted(outcomes.items()):
        if outcome != UNCHANGED:
            written.append(Written(name, outcome))


#: How many matching paths the new-rule notice lists before it gives a count.
MATCH_LIMIT = 20
TRACKED_NOTE = "still tracked; git keeps tracking it"
HIDDEN_NOTE = "untracked; now hidden from git status"
#: Variables that would point a git call in the scratch repository back at the checkout (set inside git hooks).
_REPO_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY")


class IgnoreCheckSkipped(Exception):
    """A git call the new-rule note depends on failed; the note is skipped, never guessed."""


def _new_rule_matches(git_root: Path, prefix: str, seed: str = "") -> list[tuple[str, str, str]]:
    """``(path, rule, note)`` for files already in the tree that the new ``.gitignore`` rules reach.

    Git judges both lists in throwaway ``git init`` directories that carry the
    checkout's ignore inputs: ``core.ignorecase``, ``core.excludesFile`` and
    ``info/exclude`` (see :func:`_ignore_config`).

    * **Tracked:** every tracked path that a rule the update adds (a block line
      no line of the current file already is) matches by git's pattern rules,
      whatever older rule also matches it. Ignoring never untracks.
    * **Now hidden:** every untracked path git shows today that the
      ``.gitignore`` the update would write (same seed, block position and
      preserved text, applied by :func:`apply_agent_ignores` to a byte copy,
      with every nested ``.gitignore``) ignores and the current one does not.

    The real file is never touched, so a dry run lists the same paths. Raises
    :class:`IgnoreCheckSkipped` (or ``OSError``) when inspection fails; returns
    nothing outside a git checkout.
    """
    if not (git_root / ".git").exists():
        return []
    tracked = _ls_files(git_root, [])
    untracked = _ls_files(git_root, ["--others", "--exclude-standard"])
    config, exclude = _ignore_config(git_root)
    with tempfile.TemporaryDirectory() as tmp:
        matched = _tracked_matches(Path(tmp) / "tracked", git_root, prefix, config, tracked)
        hidden = _newly_hidden(Path(tmp) / "hidden", git_root, prefix, seed, config, exclude, untracked)
    return ([(f, rule, TRACKED_NOTE) for f, rule in matched.items()]
            + [(f, rule, HIDDEN_NOTE) for f, rule in hidden.items()])


def _git(args: list[str], cwd: Path, *, stdin: str | None = None, ok: tuple[int, ...] = (0,)) -> str:
    """Raw stdout of ``git <args>``; :class:`IgnoreCheckSkipped` on any other exit."""
    env = {k: v for k, v in os.environ.items() if k not in _REPO_ENV}
    r = subprocess.run(["git", *args], cwd=cwd, input=stdin, capture_output=True, text=True,
                       check=False, timeout=60, env=env)
    if r.returncode not in ok:
        reason = (r.stderr.strip().splitlines() or [f"exit {r.returncode}"])[-1]
        command = next(a for i, a in enumerate(args) if not a.startswith("-") and (i == 0 or args[i - 1] != "-c"))
        raise IgnoreCheckSkipped(f"git {command}: {reason}")
    return r.stdout


def _ls_files(git_root: Path, args: list[str]) -> list[str]:
    return [f for f in _git(["ls-files", "-z", *args], git_root).split("\0") if f]


def _ignore_config(git_root: Path) -> tuple[list[str], Path | None]:
    """The checkout's ignore settings as ``-c`` flags, and its ``info/exclude`` file.

    ``core.ignorecase`` is always passed (``git init`` on a case-insensitive
    disk would otherwise pick its own). ``core.excludesFile`` is passed when
    the checkout sets one; unset, the scratch repository falls back to the same
    per-user default file, as it runs as the same user.
    """
    ignorecase = _git(["config", "--bool", "--get", "core.ignorecase"], git_root, ok=(0, 1)).strip() or "false"
    config = ["-c", f"core.ignorecase={ignorecase}"]
    excludes = _git(["config", "--path", "--get", "core.excludesFile"], git_root, ok=(0, 1)).strip()
    if excludes:
        config += ["-c", f"core.excludesFile={git_root / excludes}"]   # an absolute path stays absolute
    exclude = git_root / _git(["rev-parse", "--git-path", "info/exclude"], git_root).strip()
    return config, exclude if exclude.is_file() else None


def _scratch(sandbox: Path, git_root: Path, rels: list[str], exclude: Path | None) -> None:
    """``git init`` ``sandbox`` with byte copies of ``rels`` (from ``git_root``) and of ``info/exclude``."""
    sandbox.mkdir()
    _git(["init", "-q", str(sandbox)], sandbox)
    for rel in (r for r in dict.fromkeys(rels) if (git_root / r).is_file()):
        (sandbox / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(git_root / rel, sandbox / rel)
    if exclude is not None:
        shutil.copyfile(exclude, sandbox / ".git" / "info" / "exclude")


def _tracked_matches(sandbox: Path, git_root: Path, prefix: str, config: list[str],
                     tracked: list[str]) -> dict[str, str]:
    """``{path: rule}`` for tracked paths a rule new to ``.gitignore`` matches, by git's pattern rules alone."""
    path = git_root / GITIGNORE
    have = {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()} if path.is_file() else set()
    rules = [r for r in _prefixed(GITIGNORE_LINES, prefix) if r not in have]
    if not rules or not tracked:
        return {}
    _scratch(sandbox, git_root, [], None)
    (sandbox / GITIGNORE).write_text("\n".join(rules) + "\n", encoding="utf-8")
    return _ignored(sandbox, tracked, config, source=GITIGNORE)


def _newly_hidden(sandbox: Path, git_root: Path, prefix: str, seed: str, config: list[str],
                  exclude: Path | None, untracked: list[str]) -> dict[str, str]:
    """``{path: rule}`` for untracked paths the updated ``.gitignore`` ignores and the current one does not."""
    if not untracked:
        return {}
    nested = _ls_files(git_root, ["--cached", "--others", "--exclude-standard", "--", ":(glob)**/.gitignore"])
    _scratch(sandbox, git_root, [GITIGNORE, *nested], exclude)
    before = _ignored(sandbox, untracked, config)
    apply_agent_ignores(sandbox, prefix, gitignore_seed=seed)
    after = _ignored(sandbox, untracked, config)
    return {f: rule for f, rule in after.items() if f not in before}


def _ignored(sandbox: Path, paths: list[str], config: list[str], *, source: str | None = None) -> dict[str, str]:
    """``{path: rule}`` for each path git ignores in ``sandbox`` (only rules from ``source``, when given)."""
    out = _git([*config, "check-ignore", "--no-index", "-v", "-z", "--stdin"], sandbox,
               stdin="\0".join(paths) + "\0", ok=(0, 1))
    fields = out.split("\0")
    return {path: rule for src, _line, rule, path in zip(*[iter(fields)] * 4)
            if not rule.startswith("!") and (source is None or src == source)}


def print_new_rule_matches(matches: list[tuple[str, str, str]]) -> None:
    """List what the new ``.gitignore`` rules match, at most :data:`MATCH_LIMIT` then a count."""
    if not matches:
        return
    print(".gitignore: new rules match files already in the tree (nothing was untracked):")
    for path, rule, note in matches[:MATCH_LIMIT]:
        print(f"  {path} ({rule}): {note}")
    if len(matches) > MATCH_LIMIT:
        print(f"  … and {len(matches) - MATCH_LIMIT} more")
