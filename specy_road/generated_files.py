"""Files specy-road generates AND expects to be committed.

``roadmap.md`` (``specy-road export``) is the human index; ``roadmap-context.md``
(``specy-road digest``) is what an agent reads instead of crawling ``planning/``
and ``work/``. Both are regenerated from the graph, and both belong in git — a
fresh clone and CI read them before anything has been regenerated.

Adopters have gitignored them anyway, because "generated" usually implies
"untracked" (see ``docs/design-notes/v0-2-1-rc1-adopter-feedback-triage.md`` §4).
The local checkout then looks fine while CI sees the file missing. These helpers
detect that and say so once, non-fatally.
"""

from __future__ import annotations

import sys
from pathlib import Path

from specy_road.digest import DEFAULT_OUTPUT
from specy_road.git_subprocess import run as git_run

#: Repo-root-relative names that are generated and committed.
GENERATED_COMMITTED: tuple[str, ...] = ("roadmap.md", DEFAULT_OUTPUT)

#: Which command regenerates each of them, for the warning text.
_REGENERATED_BY = {
    "roadmap.md": "specy-road export",
    DEFAULT_OUTPUT: "specy-road digest",
}


def _check_ignore(root: Path, name: str, *, no_index: bool) -> bool:
    """Whether ``git check-ignore`` reports ``name``. False when git cannot say.

    Exit 0 means matched, 1 means not; 128 (not a worktree) and -1 (git missing
    or timed out) mean we have no answer, and no answer must never provoke a
    warning or change what gets staged.
    """
    args = ["check-ignore", "-q"]
    if no_index:
        args.append("--no-index")
    return git_run([*args, "--", name], root).code == 0


def ignored_generated_files(root: Path) -> list[str]:
    """The names in :data:`GENERATED_COMMITTED` that a ``.gitignore`` rule matches.

    ``--no-index`` is what makes this useful: plain ``check-ignore`` stays silent
    for a file that is already tracked, and tracked-but-ignored is exactly the
    state worth reporting — the file is committed, so it looks fine here, while
    the rule hides it from anyone who regenerates it.
    """
    return [n for n in GENERATED_COMMITTED if _check_ignore(root, n, no_index=True)]


def unstageable_generated_files(root: Path) -> list[str]:
    """The names ``git add`` would refuse: ignored **and** not yet tracked.

    Deliberately narrower than :func:`ignored_generated_files`. ``git add``
    accepts a tracked file whose path also matches an ignore rule, so skipping
    that one would strand the regenerated copy outside every commit — the drift
    this release exists to end. Only an ignored *untracked* path aborts the
    whole ``git add``, and only that one may be dropped.
    """
    return [n for n in GENERATED_COMMITTED if _check_ignore(root, n, no_index=False)]


def gitignore_resolution_hint(root: Path, name: str) -> str | None:
    """The one resolution for a generated-and-committed file an ignore rule hides.

    ``None`` when no rule matches. Every command that can trip over this state —
    ``validate``, ``finish-this-task``, ``digest --check``, ``export --check`` —
    ends on these same two steps, so an operator who meets it once recognises it
    everywhere instead of reading three partial descriptions as three different
    problems and hunting for a per-command opt-out. There is none: both names in
    :data:`GENERATED_COMMITTED` are committed by contract.
    """
    if not _check_ignore(root, name, no_index=True):
        return None
    return (
        f"{name} is matched by .gitignore, but it is generated AND committed "
        f"({_REGENERATED_BY[name]}). Remove that rule from .gitignore, then: "
        f"git add -f {name}"
    )


def warn_if_generated_files_ignored(root: Path) -> list[str]:
    """One non-fatal stderr line per generated-and-committed file that is ignored."""
    hits = ignored_generated_files(root)
    for name in hits:
        print(
            f"roadmap: warning — {gitignore_resolution_hint(root, name)} "
            "(a fresh clone and CI will otherwise see it missing)",
            file=sys.stderr,
        )
    return hits
