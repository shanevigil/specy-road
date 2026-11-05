"""The post-run write check of a reviewer run (M8.3), split from :mod:`specy_road.review_record_write` for the file
limit; callers reach these names through that module, whose docstring describes the outcomes.

:func:`snapshot` records, before and after the run, every file of the checkout the reviewer ran in, of its Git
metadata a reviewer of this leaf could change (:func:`_walk_git`) and of the leaf's hand-off directory, each as
:func:`_record` keeps it, plus ``HEAD``, the reviewed branch and the Git index's entries; :func:`written` names what
changed. Nothing is exempt: the files specy-road itself writes in that tree during the run, the transcript and
``review delegate``'s run record (:class:`OwnFile`), exist before the first snapshot and are written in place, so
no directory entry moves, and are compared by content against what specy-road wrote. Its other run files live
outside the tree (Codex's ``-o`` answer: a private temporary directory) or are only created before and written after
the run (the lock, the prompt, the schema; the notes and the record).
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
LOCK_NAME = ".review-run.lock"


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


def _walk(base: Path, state: dict[str, Any], skip: frozenset[str] = frozenset()) -> None:
    """Every file under ``base`` as :func:`_record` keeps it (identity, links, mode, size, mtime, content), and
    every directory, ``base`` included, as :func:`_dir_record` does, ignored ones included, but every path in
    ``skip`` (the checkout's own ``.git``, scoped by :func:`_walk_git`).
    A nested checkout (a directory holding ``.git``) is another repository: only its ``.git`` marker is recorded
    (:func:`_git_marker`), so a reviewer-created ``.git`` file or ``git init`` anywhere is still a write."""
    stack = [str(base)]
    while stack:
        d = stack.pop()
        try:
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


def branches(top: Path, ref: str | None = None) -> list[str]:
    """The reviewed branch's full ref name: the branch checked out at ``top`` and the local branch ``ref`` names
    (``review delegate``'s target, when the reviewer runs on a detached checkout), each once."""
    names = [git_text(["symbolic-ref", "-q", "HEAD"], top) or ""]
    if ref:
        names.append(git_text(["rev-parse", "--symbolic-full-name", ref], top) or "")
    return list(dict.fromkeys(n for n in names if n.startswith("refs/heads/")))


def _file(path: Path, state: dict[str, Any]) -> None:
    """One Git metadata file as :func:`_record` keeps it; an absent one has no entry, so its creation is a write."""
    try:
        state[str(path)] = _record(path.stat(follow_symlinks=False), str(path), path.is_symlink())
    except OSError:
        pass


def _walk_git(top: Path, state: dict[str, Any], refs: list[str]) -> None:
    """The Git metadata a reviewer of this leaf could change, and nothing other sessions of the same repository
    write: the checkout's own ``HEAD`` and ``logs/HEAD`` (in its worktree Git directory), each reviewed branch's
    loose ref, reflog and ``packed-refs`` line, the shared ``hooks/`` (code every checkout runs), and a linked
    worktree's ``.git`` pointer file. Left out: the common Git directory's own metadata, ``config``, ``objects``,
    ``FETCH_HEAD``, ``ORIG_HEAD``, other branches' refs and reflogs and other worktrees' directories, which an
    IDE's polling or another worktree's commit changes during the run; and raw index bytes, which :func:`snapshot`
    compares by their entries. A reviewer commit on the reviewed branch still moves its ref and reflog."""
    def resolved(*args: str) -> Path | None:
        out = git_text(["rev-parse", "--path-format=absolute", *args], top)
        return Path(out).resolve() if out else None
    common, own = resolved("--git-common-dir"), resolved("--git-dir")
    if own:
        _file(own / "HEAD", state)
        _file(own / "logs" / "HEAD", state)
    if common:
        packed = common / "packed-refs"
        lines = packed.read_text(encoding="utf-8", errors="replace").splitlines() if packed.is_file() else []
        for ref in refs:
            _file(common / ref, state)
            _file(common / "logs" / ref, state)
            state[f"packed-refs {ref}"] = [ln for ln in lines if ln.endswith(f" {ref}")]
        if (common / "hooks").is_dir():
            _walk(common / "hooks", state)
    pointer = top / ".git"
    if pointer.is_file():
        _file(pointer, state)


@dataclass
class Snapshot:
    """What a reviewer run could write; ``records`` keeps this model's own record bytes, ``top`` the checkout
    walked."""
    state: dict[str, Any]
    records: dict[Path, bytes] = field(default_factory=dict)
    top: Path = Path()

    def restore(self, reviews: Path, model: str) -> None:
        """Put this model's record files back as they were: a record the run filed itself never counts."""
        for p in _own_records(reviews, model):
            if p not in self.records:
                p.unlink(missing_ok=True)
        for p, data in self.records.items():
            p.write_bytes(data)


def snapshot(cwd: Path, reviews: Path, model: str, ref: str | None = None) -> Snapshot:
    """Every file and directory of the checkout at ``cwd``, its Git metadata as :func:`_walk_git` scopes it (``ref``:
    the reviewed branch or commit, :func:`branches`) and the hand-off directory ``reviews``, plus ``HEAD``, the
    reviewed branch and the Git index. The index is compared by what it records (``ls-files --stage -v``:
    each entry's mode, blob, stage and assume-unchanged / skip-worktree flag), not its bytes, which a read-only
    ``git status`` rewrites when it refreshes the stat cache."""
    top = Path(git_text(["rev-parse", "--show-toplevel"], cwd) or cwd).resolve()
    reviews = reviews.resolve()
    index = git_stdout(["ls-files", "--stage", "-v", "-z"], top) or ""
    refs = branches(top, ref)
    heads = [git_text(["rev-parse", "-q", "--verify", r], top) or "" for r in refs]
    state: dict[str, Any] = {"git refs": "\n".join([git_text(["rev-parse", "HEAD"], top) or "", *refs, *heads]),
                             "git index": hashlib.sha256(index.encode()).hexdigest()}
    _walk(top, state, frozenset({str(top / ".git")}))   # the checkout's own Git directory: _walk_git
    _walk_git(top, state, refs)
    if top not in reviews.parents:   # a reviewer in a linked worktree: the hand-off directory is the main checkout's
        _walk(reviews, state)
    return Snapshot(state, {p: p.read_bytes() for p in _own_records(reviews, model)}, top)


class OwnFile:
    """A file specy-road writes in the checked tree during a run: the transcript ``RUN-<model>.log``, appended to
    during each turn (:meth:`open`, :meth:`write`), and ``review delegate``'s ``RUN-<model>.json``, rewritten between
    turns (:meth:`rewrite`). It exists before the run's first snapshot and is written in place, so no directory entry
    moves; :func:`written` compares its identity and mode like any file's, and its content with :meth:`changed`:
    true when it is anything but what it held when the run began plus what specy-road wrote since (the harness
    rewrote, truncated, removed or appended to it), or when :meth:`rewrite` found it changed before overwriting."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.digest = hashlib.sha256(self._bytes())
        self.tampered = False

    def _bytes(self) -> bytes:
        return self.path.read_bytes() if self.path.is_file() else b""   # removed: specy-road's bytes are gone

    def open(self) -> Any:
        """The file for appending, untranslated (``newline=""``), so the bytes written are the bytes hashed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return self.path.open("a", encoding="utf-8", newline="")

    def write(self, f: Any, text: str) -> None:
        f.write(text)
        self.digest.update(text.encode("utf-8"))

    def rewrite(self, text: str) -> None:
        """Replace the content in place; a change since specy-road's last write is kept as :attr:`tampered`."""
        self.tampered = self.tampered or self.changed()
        with self.path.open("w", encoding="utf-8", newline="") as f:
            f.write(text)
        self.digest = hashlib.sha256(text.encode("utf-8"))

    def changed(self) -> bool:
        return self.tampered or hashlib.sha256(self._bytes()).digest() != self.digest.digest()


#: The leading :func:`_record` fields specy-road's in-place writes leave alone: device, inode, link count, mode.
_IDENTITY = 4


def written(before: Snapshot, after: Snapshot, own: tuple[OwnFile, ...] = ()) -> list[str]:
    """Each path (or ``git refs``, ``git index``) added, removed or changed between the two snapshots; an
    :class:`OwnFile` by identity and mode here and by :meth:`OwnFile.changed` for its content. Shown relative to
    the checkout when it is inside it."""
    mine = {str(o.path.resolve()): o for o in own}
    keys = set(before.state) | set(after.state)
    changed = [k for k in keys if (before.state.get(k) != after.state.get(k) if k not in mine else
                                   (before.state.get(k) or ())[:_IDENTITY] != (after.state.get(k) or ())[:_IDENTITY]
                                   or mine[k].changed())]
    changed += [p for p, o in mine.items() if p not in keys and o.changed()]
    top = f"{before.top}{os.sep}"
    return sorted({"." if k == str(before.top) else k.removeprefix(top) for k in changed})
