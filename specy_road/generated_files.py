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


def ignored_generated_files(root: Path) -> list[str]:
    """The names in :data:`GENERATED_COMMITTED` that ``.gitignore`` matches.

    ``--no-index`` is what makes this useful: plain ``check-ignore`` stays
    silent for a file that is already tracked, which is exactly the case we
    need to flag (committed, and also matched by a rule, so a teammate who
    regenerates it sees nothing to add). Silent outside a git worktree.
    """
    hits: list[str] = []
    for name in GENERATED_COMMITTED:
        result = git_run(["check-ignore", "--no-index", "-q", "--", name], root)
        # 0 = matched by a rule, 1 = not matched; 128 (not a repo) and -1
        # (git missing/timeout) mean we cannot trust the answer.
        if result.code == 0:
            hits.append(name)
    return hits


def warn_if_generated_files_ignored(root: Path) -> list[str]:
    """One non-fatal stderr line per generated-and-committed file that is ignored."""
    hits = ignored_generated_files(root)
    for name in hits:
        print(
            f"roadmap: warning — {name} is matched by .gitignore, but it is "
            f"generated AND committed ({_REGENERATED_BY[name]}). A fresh clone "
            "and CI will see it missing. Remove the rule, then: "
            f"git add -f {name}",
            file=sys.stderr,
        )
    return hits
