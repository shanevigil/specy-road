"""The post-run write check of a reviewer run (M8.3), split from :mod:`specy_road.review_record_write` for the file
limit; callers reach these names through that module, whose docstring describes the outcomes.

:func:`snapshot` records, before and after the run, every file of the checkout the reviewer ran in, of its Git
directories (:func:`_walk_git`) and of the leaf's hand-off directory, each as :func:`_record` keeps it, plus every ref and the Git index's entries; :func:`written` names what changed, but the run's own
:func:`runtime_files`.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_stdout, git_text
from specy_road.review_files import HISTORY_DIRNAME, REVIEW_PREFIX

OUTPUT_SCHEMA_NAME = "review-output.schema.json"
OUTPUT_PREFIX = "OUTPUT-"
LOCK_NAME = ".review-run.lock"


def runtime_files(reviews: Path, model: str) -> frozenset[str]:
    """The files a reviewer run may change: its notes and what the adapter writes during the run (the run
    record ``review_delegate.RUN_PREFIX`` names and its temporary copy, the raw log, Codex's ``-o`` file, the
    output schema and :data:`LOCK_NAME`). Prompts and packets are written before the run starts."""
    names = (f"notes-{model}.md", f"RUN-{model}.json", f"RUN-{model}.json.tmp", f"RUN-{model}.log",
             f"{OUTPUT_PREFIX}{model}.json", OUTPUT_SCHEMA_NAME, LOCK_NAME)
    return frozenset(str(reviews / n) for n in names)


def _own_records(reviews: Path, model: str) -> list[Path]:
    """This model's live record, in any case, and its ``history/`` copies."""
    live = [p for p in reviews.iterdir() if p.name.lower() == f"{REVIEW_PREFIX}{model}.md".lower()] \
        if reviews.is_dir() else []
    hist = reviews / HISTORY_DIRNAME
    return live + (sorted(hist.glob(f"*-{model}.md")) if hist.is_dir() else [])


def _content(path: str, is_link: bool) -> str:
    """SHA-256 of the file's bytes (a symlink's target text): a same-length rewrite with its mtime put back
    still differs. ``unreadable`` when it cannot be read (removed mid-walk, no permission)."""
    try:
        if is_link:
            return hashlib.sha256(os.readlink(path).encode()).hexdigest()
        with open(path, "rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()
    except OSError:
        return "unreadable"


def _record(st: os.stat_result, path: str, is_link: bool) -> tuple[Any, ...]:
    """One file as the snapshot keeps it: its identity and links (device, inode, link count: a file swapped for a
    hard link to an identical copy elsewhere differs), mode (a ``chmod`` alone differs), size, mtime, change time
    and content. A process can put the mtime back but not the change time (``st_ctime_ns`` on POSIX: inode change
    time), so an identical-bytes rewrite with its mtime restored differs too."""
    return (st.st_dev, st.st_ino, st.st_nlink, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns,
            _content(path, is_link))


def _dir_record(st: os.stat_result) -> tuple[Any, ...]:
    """One directory: identity, links, mode, mtime and change time. Creating, renaming or deleting an entry moves
    its mtime and ctime, so a file the run created and deleted again still shows as a write of its directory."""
    return ("dir", st.st_dev, st.st_ino, st.st_nlink, st.st_mode, st.st_mtime_ns, st.st_ctime_ns)


def _git_marker(path: str, state: dict[str, Any]) -> None:
    """A nested checkout's ``.git``: a pointer file as any file, a directory as present only (its own repository's
    activity moves its times). Its appearing, changing or going away is a write."""
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return
    is_dir = os.path.isdir(path) and not os.path.islink(path)
    state[path] = ("checkout",) if is_dir else _record(st, path, os.path.islink(path))


def _walk(base: Path, state: dict[str, Any], skip: frozenset[str] = frozenset(),
          quiet: frozenset[str] = frozenset()) -> None:
    """Every file under ``base`` as :func:`_record` keeps it (identity, links, mode, size, mtime, content), and
    every directory, ``base`` included, as :func:`_dir_record` does, ignored ones included, but every path in
    ``skip`` (the checkout's own ``.git``, walked by :func:`_walk_git`) and the own metadata of each directory in
    ``quiet`` (:func:`snapshot`: entries are created there during an honest run), whose contents are still walked.
    A nested checkout (a directory holding ``.git``) is another repository: only its ``.git`` marker is recorded
    (:func:`_git_marker`), so a reviewer-created ``.git`` file or ``git init`` anywhere is still a write."""
    stack = [str(base)]
    while stack:
        d = stack.pop()
        try:
            if d not in quiet:
                state[d] = _dir_record(os.stat(d, follow_symlinks=False))
            entries = list(os.scandir(d))
        except OSError:   # unreadable, or removed while walking
            continue
        for e in entries:
            try:
                if e.path in skip:
                    continue
                if e.is_dir(follow_symlinks=False):
                    marker = os.path.join(e.path, ".git")
                    if os.path.lexists(marker):
                        _git_marker(marker, state)
                    else:
                        stack.append(e.path)
                    continue
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            state[e.path] = _record(st, e.path, e.is_symlink())


def _walk_git(top: Path, state: dict[str, Any], quiet: frozenset[str] = frozenset()) -> None:
    """The checkout's Git metadata: every file of its common Git directory (hooks, config, info, objects, refs,
    logs) and of its own worktree Git directory, and its ``.git`` pointer file in a linked worktree. Skipped: the
    other linked worktrees' directories under ``<common>/worktrees`` (other checkouts), and raw index bytes (this
    checkout's, which a read-only ``git status`` rewrites and :func:`snapshot` compares by its entries instead, and
    the main checkout's when this one is linked). Their directories are recorded like any other: the reviewer runs
    with ``GIT_OPTIONAL_LOCKS=0`` (:func:`~specy_road.review_record_write.reviewer_env`), so a read-only
    ``git status`` takes no ``index.lock`` there, and a file created and deleted in a Git directory root is a write."""
    def resolved(*args: str) -> Path | None:
        out = git_text(["rev-parse", "--path-format=absolute", *args], top)
        return Path(out).resolve() if out else None
    common, own, index = resolved("--git-common-dir"), resolved("--git-dir"), resolved("--git-path", "index")
    other = (common / "index", common / "worktrees") if common else ()   # the main checkout's index; other worktrees
    skip = frozenset(str(p) for p in (index, *other) if p)
    for d in dict.fromkeys(d for d in (common, own) if d):   # one directory when the checkout is the main one
        _walk(d, state, skip, quiet)
    pointer = top / ".git"
    if pointer.is_file():
        st = pointer.stat()
        state[str(pointer)] = _record(st, str(pointer), False)


@dataclass
class Snapshot:
    """What a reviewer run could write; ``records`` keeps this model's own record bytes, ``exempt``
    :func:`runtime_files`, ``top`` the checkout walked."""
    state: dict[str, Any]
    records: dict[Path, bytes] = field(default_factory=dict)
    exempt: frozenset[str] = frozenset()
    top: Path = Path()

    def restore(self, reviews: Path, model: str) -> None:
        """Put this model's record files back as they were: a record the run filed itself never counts."""
        for p in _own_records(reviews, model):
            if p not in self.records:
                p.unlink(missing_ok=True)
        for p, data in self.records.items():
            p.write_bytes(data)


def snapshot(cwd: Path, reviews: Path, model: str) -> Snapshot:
    """Every file and directory of the checkout at ``cwd``, of its Git directories (:func:`_walk_git`) and of the
    hand-off directory ``reviews``, plus every ref and the Git index. The index is compared by what it records (``ls-files --stage -v``:
    each entry's mode, blob, stage and assume-unchanged / skip-worktree flag), not its bytes, which a read-only
    ``git status`` rewrites when it refreshes the stat cache."""
    top = Path(git_text(["rev-parse", "--show-toplevel"], cwd) or cwd).resolve()
    reviews = reviews.resolve()
    index = git_stdout(["ls-files", "--stage", "-v", "-z"], top) or ""
    state: dict[str, Any] = {"git refs": (git_text(["rev-parse", "HEAD"], top) or "") + "\n"
                             + (git_text(["for-each-ref", "--format=%(refname) %(objectname)"], top) or ""),
                             "git index": hashlib.sha256(index.encode()).hexdigest()}
    # The hand-off directory's own metadata moves between harness turns (the run record's temporary file and
    # rename): its files and subdirectories are compared here, and its own metadata during each turn by RootFence.
    quiet = frozenset({str(reviews)})
    _walk(top, state, frozenset({str(top / ".git")}), quiet)   # the checkout's own Git directory: _walk_git
    _walk_git(top, state, quiet)
    if top not in reviews.parents:   # a reviewer in a linked worktree: the hand-off directory is the main checkout's
        _walk(reviews, state, quiet=quiet)
    return Snapshot(state, {p: p.read_bytes() for p in _own_records(reviews, model)}, runtime_files(reviews, model), top)


def harness_files(reviews: Path, model: str) -> tuple[str, ...]:
    """The files a reviewer's harness may create or replace in the hand-off root during its turn: Codex's ``-o``
    answer and the reviewer's notes (the other :func:`runtime_files` are specy-road's, written between turns)."""
    return (f"{OUTPUT_PREFIX}{model}.json", f"notes-{model}.md")


class RootFence:
    """The hand-off root's own metadata across one harness turn. specy-road changes that directory's entries only
    between turns (the run record's rename, the schema file), so a move of its mtime, ctime or link count during the
    turn is the harness's: a file created, renamed or deleted there. It is explained only by one of
    :func:`harness_files` appearing, going or being replaced in the same turn (which then also hides any other such
    change in that turn); otherwise :meth:`moved` is true and the run is a review failure."""

    def __init__(self, root: Path, allowed: tuple[str, ...]) -> None:
        self.root, self.allowed = root, allowed
        self.before = self._state()

    def _state(self) -> tuple[Any, ...] | None:
        try:
            st = os.stat(self.root)
        except OSError:
            return None
        ids = []
        for name in self.allowed:
            try:
                f = os.stat(self.root / name, follow_symlinks=False)
                ids.append((f.st_dev, f.st_ino))
            except OSError:
                ids.append(None)
        return (st.st_mtime_ns, st.st_ctime_ns, st.st_nlink), tuple(ids)

    def moved(self) -> bool:
        after = self._state()
        if after is None or self.before is None:
            return after != self.before
        return after[0] != self.before[0] and after[1] == self.before[1]


def written(before: Snapshot, after: Snapshot) -> list[str]:
    """Each path (or ``git refs``, ``git index``) added, removed or changed between the two snapshots, but the run's own
    :func:`runtime_files`; shown relative to the checkout when it is inside it."""
    keys = set(before.state) | set(after.state)
    changed = (k for k in keys if k not in before.exempt and before.state.get(k) != after.state.get(k))
    top = f"{before.top}{os.sep}"
    return sorted("." if k == str(before.top) else k.removeprefix(top) for k in changed)
