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

Paths are compared as text and no symlink is followed: an entry is excluded only when its path, as ``git status``
prints it, lies under the hand-off directory, whose place is fixed before the run (:func:`snapshot`). specy-road
never makes a symlink in the hand-off directory, so any symlink there after the run (the directory itself, a
subdirectory, or a file at an excluded name) is a review failure, and :meth:`Snapshot.restore` removes it.

specy-road's own writes there once the reviewer has started never follow a symlink either: :func:`replace_file`
renames a fresh file over the path (a symlink at the path is replaced, not written through), :func:`append_log`
refuses to open a symlink, and :func:`real_dirs` turns a symlinked directory back into a real one first.
"""

from __future__ import annotations

import errno
import hashlib
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.review_files import HISTORY_DIRNAME, REVIEW_PREFIX

OUTPUT_SCHEMA_NAME = "review-output.schema.json"
LOCK_NAME = ".review-run.lock"
#: How :func:`_handoff` marks a symlink, which :func:`written` always reports.
SYMLINK = "symlink "


def _own_records(reviews: Path, model: str) -> list[Path]:
    """This model's live record, in any case, and its ``history/`` copies."""
    live = [p for p in reviews.iterdir() if p.name.lower() == f"{REVIEW_PREFIX}{model}.md".lower()] \
        if reviews.is_dir() else []
    hist = reviews / HISTORY_DIRNAME
    return live + (sorted(hist.glob(f"*-{model}.md")) if hist.is_dir() else [])


def replace_file(path: Path, data: bytes | str) -> None:
    """Make ``path`` a regular file holding ``data`` without following a symlink at ``path``: write a temporary file
    created exclusively beside it, then rename it over ``path`` (a rename replaces a symlink, never its target). A
    symlinked parent directory is refused (``ELOOP``): the write would land wherever it points. Callers pass paths
    they derive themselves (node id, model, hand-off directory), never a path read from a file."""
    if path.parent.is_symlink():
        raise OSError(errno.ELOOP, "refusing to write through a symlinked directory", str(path.parent))
    raw = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_log(path: Path) -> Any:
    """``path`` opened for appending text, untranslated, but never through a symlink: one there (a reviewer's) is not
    written through, the turn's output goes nowhere, and the tripwire reports the symlink."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o644)
    except OSError as e:
        if e.errno != errno.ELOOP and not path.is_symlink():
            raise
        return open(os.devnull, "a", encoding="utf-8", newline="")
    return os.fdopen(fd, "a", encoding="utf-8", newline="")


def real_dirs(base: Path, d: Path) -> None:
    """Every directory from ``base`` down to ``d`` a real directory: a symlink there is removed (never followed), and
    a missing directory or one that replaced it is made."""
    rel = d.relative_to(base).parts
    for p in (base.joinpath(*rel[:n]) for n in range(len(rel) + 1)):
        if p.is_symlink() or (p.exists() and not p.is_dir()):
            p.unlink()
        p.mkdir(exist_ok=True)


def _symlinks(reviews: Path) -> list[Path]:
    """Each symlink in the hand-off directory, the directory itself included; none is followed."""
    if reviews.is_symlink():
        return [reviews]
    out: list[Path] = []
    for d, dirs, names in os.walk(reviews):
        out += [Path(d) / n for n in [*dirs, *names] if (Path(d) / n).is_symlink()]
    return out


def _hash(path: Path) -> str:
    """SHA-256 of a file's bytes; of a symlink's target text, never what it points at (no link is followed)."""
    try:
        if path.is_symlink():
            return hashlib.sha256(os.readlink(path).encode()).hexdigest()
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:   # a directory (a new untracked repository), or removed meanwhile
        return "unreadable"


def _status(top: Path, handoff: PurePosixPath | None) -> dict[str, str]:
    """Each path ``git status`` lists at ``top``, as its status code and :func:`_hash`. An entry is left to
    :func:`_handoff` only when its path, **as git prints it**, is under ``handoff`` (the hand-off directory relative
    to ``top``, or ``None`` when it lies outside the checkout): the decision is lexical, so a tracked file swapped for
    a symlink into the hand-off directory (``T``) is still the reviewer's write."""
    out = (git_stdout(["status", "--porcelain", "-z", "--untracked-files=all"], top) or "").split("\0")
    state: dict[str, str] = {}
    entries = iter(out)
    for e in entries:
        if not e:
            continue
        code, rel = e[:2], e[3:]
        if "R" in code or "C" in code:   # a rename or copy: the next field is its source path
            next(entries, None)
        parts = PurePosixPath(rel.rstrip("/")).parts
        if handoff is None or parts[:len(handoff.parts)] != handoff.parts:
            state[rel] = f"{code} {_hash(top / rel)}"
    return state


def _handoff(reviews: Path, model: str, top: Path) -> dict[str, str]:
    """Each file under the hand-off directory by :func:`_hash`, but the notes and specy-road's run files directly in
    it. Nothing is followed: a symlinked directory is one entry (its target text), not a walk into its target; the
    hand-off directory itself replaced by a symlink is an entry too."""
    skip = {f"notes-{model}.md", f"RUN-{model}.json", f"RUN-{model}.log", LOCK_NAME}
    def shown(p: Path) -> str:
        return str(p.relative_to(top)) if p.is_relative_to(top) else str(p)
    links = _symlinks(reviews)
    files: list[Path] = [] if reviews in links else [
        Path(d) / n for d, _dirs, names in os.walk(reviews)   # followlinks=False: a symlinked directory is not walked
        for n in names if not (Path(d) == reviews and n in skip) and not (Path(d) / n).is_symlink()]
    # A symlink is never specy-road's: one at any name, an excluded one included, is always a write (:func:`written`).
    return {shown(p): _hash(p) for p in sorted(files)} | {shown(p): SYMLINK + _hash(p) for p in links}


@dataclass
class Snapshot:
    """What the tripwire compares; ``records`` keeps this model's own record bytes, ``top`` the checkout and
    ``reviews`` the hand-off directory, both fixed by the snapshot before the run (:func:`snapshot`)."""
    state: dict[str, str]
    records: dict[Path, bytes] = field(default_factory=dict)
    top: Path = Path()
    reviews: Path = Path()

    def with_symlinks(self, paths: list[Path]) -> Snapshot:
        """This snapshot plus symlinks specy-road found at its own files during the run and replaced rather than
        followed (``review delegate``'s between-turn run-record update), which :func:`written` then reports."""
        for p in paths:
            self.state[str(p.relative_to(self.top)) if p.is_relative_to(self.top) else str(p)] = SYMLINK + "replaced"
        return self

    def restore(self, reviews: Path, model: str) -> None:
        """After a review failure: remove every symlink in the hand-off directory (none is followed; a symlinked
        directory, the hand-off directory itself included, becomes a real one again), then put this model's record
        files back as they were (:func:`replace_file`): a record the run filed itself never counts. ``reviews`` is
        the caller's path; the place fixed before the run (:attr:`reviews`) is used when the snapshot has one."""
        reviews = self.reviews if self.reviews != Path() else reviews
        for link in sorted(_symlinks(reviews), key=lambda q: len(q.parts), reverse=True):
            link.unlink()
        for p in self.records:
            real_dirs(reviews, p.parent)
        real_dirs(reviews, reviews)
        for p in _own_records(reviews, model):
            if p not in self.records:
                p.unlink(missing_ok=True)
        for p, data in self.records.items():
            replace_file(p, data)


def snapshot(cwd: Path, reviews: Path, model: str, like: Snapshot | None = None) -> Snapshot:
    """The leaf worktree's ``git status`` at ``cwd`` and the hand-off directory ``reviews`` (module docstring).

    Where the checkout and the hand-off directory are is decided once, before the run, by the first snapshot (the
    checkout git reports, and the hand-off directory's real path, which specy-road created); the snapshot after
    the run passes it as ``like`` and reuses both, so nothing the reviewer could have changed is resolved or
    followed. Each entry's path is then compared as text."""
    if like is not None:
        top, real = like.top, like.reviews
    else:
        top = Path(git_text(["rev-parse", "--show-toplevel"], cwd) or os.path.abspath(cwd))
        real = reviews.resolve()   # before the run: specy-road's own directory
    handoff = PurePosixPath(real.relative_to(top).as_posix()) if real.is_relative_to(top) else None
    state = {**_status(top, handoff), **_handoff(real, model, top)}
    return Snapshot(state, {p: p.read_bytes() for p in _own_records(real, model)}, top, real)


def written(before: Snapshot, after: Snapshot) -> list[str]:
    """Each path added, removed or changed between the two snapshots, and each symlink in the hand-off directory
    after the run, changed or not; relative to the checkout when inside it."""
    keys = set(before.state) | set(after.state)
    return sorted(k for k in keys if before.state.get(k) != after.state.get(k)
                  or after.state.get(k, "").startswith(SYMLINK))
