"""The tripwire after a reviewer run (M8.3 A2), split from :mod:`specy_road.review_record_write` for the file
limit; callers reach these names through that module.

Prevention is the boundary, not this module: specy-road files ``REVIEW-<model>.md`` from the run's final JSON, and
each adapter's reviewer launch has no write access (Codex ``sandbox_mode=read-only``; Cursor ``--mode ask``
without ``--force``; Claude Code with ``Write``, ``Edit`` and ``NotebookEdit`` denied beside the commit, push and
``gh`` bans). This is a tripwire for what slips past it, **not a security boundary**. :func:`snapshot` runs
before and after the run, and :func:`written` reports a review failure when:

* the leaf worktree's ``git status --porcelain -z --untracked-files=all`` lists a path it did not list before, or
  lists one with another status code or other content (a changed tracked file, a new untracked file); or
* the hand-off directory ``work/reviews/<ID>/`` gains, loses or changes (by SHA-256 of its bytes) any file other
  than the reviewer's notes (``notes-<model>.md``) and the run files specy-road itself writes during the run
  (``RUN-<model>.json``, ``RUN-<model>.log``, the run lock).

Out of scope, by design: identical-byte rewrites, writes undone before the run ends, metadata-only changes (mode,
times, links), git-ignored files outside the hand-off directory, and Git internals (``HEAD``, refs, reflogs, the
index, hooks, config). A reviewer that commits is stopped by the launch's bans, not detected here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.review_files import HISTORY_DIRNAME, REVIEW_PREFIX

OUTPUT_SCHEMA_NAME = "review-output.schema.json"
LOCK_NAME = ".review-run.lock"


def _own_records(reviews: Path, model: str) -> list[Path]:
    """This model's live record, in any case, and its ``history/`` copies."""
    live = [p for p in reviews.iterdir() if p.name.lower() == f"{REVIEW_PREFIX}{model}.md".lower()] \
        if reviews.is_dir() else []
    hist = reviews / HISTORY_DIRNAME
    return live + (sorted(hist.glob(f"*-{model}.md")) if hist.is_dir() else [])


def _hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:   # a directory (a new untracked repository), or removed meanwhile
        return "unreadable"


def _status(top: Path, reviews: Path) -> dict[str, str]:
    """Each path ``git status`` lists at ``top``, as its status code and content hash; the hand-off directory is
    left to :func:`_handoff` (its run files change during every run)."""
    out = (git_stdout(["status", "--porcelain", "-z", "--untracked-files=all"], top) or "").split("\0")
    state: dict[str, str] = {}
    entries = iter(out)
    for e in entries:
        if not e:
            continue
        code, rel = e[:2], e[3:]
        if "R" in code or "C" in code:   # a rename or copy: the next field is its source path
            next(entries, None)
        path = top / rel
        if path.resolve() != reviews and reviews not in path.resolve().parents:
            state[rel] = f"{code} {_hash(path)}"
    return state


def _handoff(reviews: Path, model: str, top: Path) -> dict[str, str]:
    """Each file under the hand-off directory by content hash, but the notes and specy-road's run files."""
    skip = {f"notes-{model}.md", f"RUN-{model}.json", f"RUN-{model}.log", LOCK_NAME}
    files = sorted(p for p in reviews.rglob("*") if p.is_file() and not (p.parent == reviews and p.name in skip)) \
        if reviews.is_dir() else []
    return {(str(p.relative_to(top)) if top in p.parents else str(p)): _hash(p) for p in files}


@dataclass
class Snapshot:
    """What the tripwire compares; ``records`` keeps this model's own record bytes, ``top`` the checkout."""
    state: dict[str, str]
    records: dict[Path, bytes] = field(default_factory=dict)
    top: Path = Path()

    def restore(self, reviews: Path, model: str) -> None:
        """Put this model's record files back as they were: a record the run filed itself never counts."""
        for p in _own_records(reviews, model):
            if p not in self.records:
                p.unlink(missing_ok=True)
        for p, data in self.records.items():
            p.write_bytes(data)


def snapshot(cwd: Path, reviews: Path, model: str) -> Snapshot:
    """The leaf worktree's ``git status`` at ``cwd`` and the hand-off directory ``reviews`` (module docstring)."""
    top = Path(git_text(["rev-parse", "--show-toplevel"], cwd) or cwd).resolve()
    reviews = reviews.resolve()
    state = {**_status(top, reviews), **_handoff(reviews, model, top)}
    return Snapshot(state, {p: p.read_bytes() for p in _own_records(reviews, model)}, top)


def written(before: Snapshot, after: Snapshot) -> list[str]:
    """Each path added, removed or changed between the two snapshots, relative to the checkout when inside it."""
    keys = set(before.state) | set(after.state)
    return sorted(k for k in keys if before.state.get(k) != after.state.get(k))
