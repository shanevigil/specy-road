"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.extracted.history_walk import commit
from tests.support.extracted.history_walk import git

def _gate_commit(repo: Path, codename: str, tally: str | None = None) -> None:
    """A leaf's gate commit as mark-implementation-reviewed writes it: a registry-only change, a tally trailer."""
    with (repo / "roadmap" / "registry.yaml").open("a", encoding="utf-8") as fh:
        fh.write(f"# gate {codename}\n")
    trailers = "Reviewed-by: human (human) approve abc1234" + (f"\nReview-tally: {tally}" if tally else "")
    commit(repo, f"chore(rm-{codename}): mark implementation reviewed\n\n{trailers}")

def _complete(repo: Path, codename: str) -> None:
    """finish-this-task's bookkeeping commit; on its own it lands nothing."""
    with (repo / "roadmap" / "registry.yaml").open("a", encoding="utf-8") as fh:
        fh.write(f"# done {codename}\n")
    commit(repo, f"chore(rm-{codename}): complete, deregister")

def finish_merge(repo: Path, codename: str, into: str = "main") -> None:
    """The merge finish-this-task lands a leaf with; like finish, the registry keeps the integration side."""
    git(repo, "checkout", "-q", into)
    git(repo, "merge", "-q", "--no-ff", "-X", "ours", "-m", f"Merge branch 'feature/rm-{codename}' into {into}",
        f"feature/rm-{codename}")

def land(repo: Path, codename: str, tally: str | None = None, into: str = "main") -> None:
    """A leaf's branch off ``into`` with its gate and completion commits, merged back as finish does."""
    git(repo, "checkout", "-q", "-b", f"feature/rm-{codename}", into)
    _gate_commit(repo, codename, tally)
    _complete(repo, codename)
    finish_merge(repo, codename, into)
