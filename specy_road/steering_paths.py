"""Steering files: what an executor can write that trusted code outside it later reads or runs (M22.5).

An unattended executor works in a linked worktree, and some files it can write are read or run later by
something it does not control: git reads hooks and ``core.fsmonitor`` / ``core.hooksPath`` from the common git
dir, which every worktree of the repository shares. This module holds the git-steering part of the one list
(documented in docs/orchestration-steering-files.md, linked from docs/orchestration-workers.md) and the per-turn
snapshot (:func:`git_snapshot`) that the post-run check (:class:`~specy_road.worker_turn_check.SteeringWatch`)
takes per worker turn, in the worktree and in the main checkout, and compares as ``steering_file`` findings. It is
read from the filesystem only, at the turn's start and at its end, so it is compared before any post-turn git
command runs.

Detection only: nothing here restores a changed file. Paths compare project-relative, as ``zone_matches``
does, and one real path is stored once.

**One rule for any input that cannot be read** (:func:`guarded`): every per-file and per-directory step (listing,
reading, decoding, parsing, hashing) runs on its own, and any exception there (a permission error, a special file
such as a FIFO, a dangling link or a link loop where a file or directory is named, a file over :data:`MAX_PARSE_BYTES`, a file gone mid-read, the
snapshot past :data:`SNAPSHOT_SECONDS`, a hooks directory over :data:`HOOKS_CAP` entries) records that path and its
class as unreadable (an ``error:`` value) and the snapshot goes on with every other path. The comparison reports
each such path as a ``check_error`` finding (path and class) and never as unchanged; it counts as git steering not
verified, so no post-turn git command runs. Only a path that does not exist is ``absent``: a config file a read
config names is recorded so, so its creation or deletion compares under an unchanged includer; an entry missing from
one end altogether is compared only where what lists or includes it was read in full there (:func:`compared`).

**Links are entries of their own** (:func:`_link`): a file or hooks directory is stored once, by the real path it
resolves to, and each name git reads it by that is not that real path (a symlink on the way) is also recorded, as
``link:<real path>``. A link created, removed or retargeted is therefore a change of that name, whatever the real
paths at each end. The same holds for a checkout's ``.git``: its value names the gitdir and common dir it leads to.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from specy_road.git_config_text import read_chain, watched_values
from specy_road.runtime_paths import prefix_within
from specy_road.worktree_env import git_top, main_project_root

#: The sticky worker flag a ``steering_file`` finding sets; only ``worker reconcile`` (without ``--dismiss``) clears it.
FLAG_STEERING = "steering_changed"
#: Every ``class`` a ``steering_file`` finding can carry.
CLASSES = ("git_hook", "git_config")
#: A hooks directory with more direct children than this is unreadable on every comparison (fails closed); its
#: listing stops after ``HOOKS_CAP + 1`` entries.
HOOKS_CAP = 200
ABSENT = "absent"
#: The prefix of a value that could not be read (:func:`guarded`).
ERROR = "error:"
#: The prefix of a container's value (a checkout's ``.git``, a hooks directory) read in full: what an entry's
#: ``parent`` names. An entry's absence at one end is a change only when its parent is read there (:func:`compared`).
READ = "read:"
#: Files this module parses (``.git`` files, git config) larger than this are unreadable, not parsed.
MAX_PARSE_BYTES = 8 * 1024 * 1024
#: One snapshot's time budget: every path read after it is spent is unreadable (a timeout), never skipped.
SNAPSHOT_SECONDS = 30.0
_CHUNK = 1 << 20

_until = float("inf")   # the running snapshot's deadline (:func:`git_snapshot` sets it)


def _in_time() -> None:
    if time.monotonic() > _until:
        raise TimeoutError(f"git-steering snapshot over {SNAPSHOT_SECONDS:.0f}s")


def _open_regular(path: Path) -> int:
    """A read descriptor on ``path``, which must be a regular file once open: a FIFO, socket or device is refused
    without blocking (``O_NONBLOCK``), and so is one swapped in after any earlier ``stat``."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError("not a regular file (special file)")
    return fd


def _digest(path: Path) -> str:
    """A regular file's sha256, streamed (size is never a reason to fail), within the snapshot's time budget."""
    h = hashlib.sha256()
    with os.fdopen(_open_regular(path), "rb") as f:
        while chunk := f.read(_CHUNK):
            _in_time()
            h.update(chunk)
    return h.hexdigest()


def parse_bytes(path: Path) -> bytes:
    """A regular file this module parses, refused over :data:`MAX_PARSE_BYTES`."""
    _in_time()
    with os.fdopen(_open_regular(path), "rb") as f:
        data = f.read(MAX_PARSE_BYTES + 1)
    if len(data) > MAX_PARSE_BYTES:
        raise ValueError(f"over the {MAX_PARSE_BYTES} byte parse cap")
    return data


def one_line(text: str) -> str:
    """``text`` as one line of text output: a backslash and every character that is not printable (a newline, a
    line separator, a control character) escaped, so a value read from an executor's file cannot start a line."""
    return "".join(c if c.isprintable() and c != "\\" else c.encode("unicode_escape").decode("ascii") for c in text)


def resolved_path(path: Path) -> Path:
    """``path`` resolved without raising: a link loop or a missing part (an executor can make either) stays as named."""
    return Path(os.path.realpath(path))


def _hook_value(path: Path) -> str | None:
    """A hooks-directory entry as it compares: the sha256 of the regular file it is (a link followed, so a write
    through an unchanged link changes it); ``None`` for a directory (not a hook). Raises for anything else (a
    special file, a dangling link or a loop): :func:`guarded` records that."""
    mode = os.stat(path).st_mode
    return None if stat.S_ISDIR(mode) else _digest(path)


def real_path(path: Path) -> Path:
    """``path`` with its parent resolved and its last component kept: a link is recorded, not followed."""
    return Path(os.path.realpath(path.parent)) / path.name


@dataclass(frozen=True)
class Entry:
    path: str                 # as findings name it: project-relative in the worker's tree, else absolute
    cls: str
    value: str
    values: tuple[tuple[str, str], ...] = ()   # git_config only: the watched keys' values
    parent: str | None = None   # the key of what listed or included it: a hooks directory, a config file, ``.git``


Snapshot = dict[str, Entry]   # keyed by the real path


def _gitdirs(top: Path) -> tuple[Path, Path]:
    """``(worktree gitdir, common git dir)`` of the checkout at ``top``, read from ``.git`` without running git;
    raises when ``.git`` names neither, or either is not an existing directory (the checkout's git steering cannot
    be read: a missing gitdir or ``commondir`` target is unreadable, never an empty git dir)."""
    dotgit = top / ".git"
    if dotgit.is_dir():
        return resolved_path(dotgit), resolved_path(dotgit)
    line = parse_bytes(dotgit).decode("utf-8").strip()
    if not line.startswith("gitdir:"):
        raise ValueError("no gitdir: line")
    gitdir = resolved_path(top / line.removeprefix("gitdir:").strip())
    commondir = gitdir / "commondir"
    common = resolved_path(gitdir / parse_bytes(commondir).decode("utf-8").strip()) if os.path.lexists(commondir) \
        else gitdir   # a commondir that cannot be read (a dangling link included) raises, never reads as missing
    for d in (gitdir, common):
        if not d.is_dir():
            raise NotADirectoryError(f"git dir {d} is not a directory")
    return gitdir, common


@dataclass(frozen=True)
class Scope:
    """Where one worker's steering files live: its worktree and the main checkout, the same project prefix."""
    prefix: str
    w_top: Path
    m_top: Path

    @property
    def tops(self) -> list[Path]:
        return [self.w_top] if self.m_top == self.w_top else [self.w_top, self.m_top]

    def display(self, real: Path) -> str:
        """Project-relative in the worker's tree (git-root-relative outside its project), else absolute."""
        for base in (self.w_top / self.prefix, self.w_top):
            if real.is_relative_to(base):
                return real.relative_to(base).as_posix()
        return str(real)


def _error(e: BaseException) -> str:
    return f"{ERROR}{type(e).__name__}: {e}"


def scope_for(repo_root: Path, worktree: Path) -> Scope:
    """The worker's scope, taken at the turn's start from the filesystem (no git command)."""
    m_root = resolved_path(main_project_root(Path(repo_root)))
    m_top, w_top = git_top(m_root), git_top(Path(worktree))
    return Scope(prefix_within(m_top, m_root), w_top, m_top)


def guarded(snap: Snapshot, scope: Scope, path: Path, cls: str, step: Callable[[], None]) -> None:
    """Run one per-file or per-directory ``step``; any exception records ``path`` as unreadable for ``cls``
    (the module's one rule) and the snapshot goes on."""
    try:
        _in_time()
        step()
    except Exception as e:  # noqa: BLE001 — one rule: an unreadable input is reported, never fatal
        unreadable(snap, scope, path, cls, e)


def unreadable(snap: Snapshot, scope: Scope, path: Path, cls: str, e: BaseException) -> None:
    """Record ``path`` as unreadable for ``cls``, replacing whatever was recorded for it."""
    real = real_path(path)
    snap[str(real)] = Entry(scope.display(real), cls, _error(e))


def _read(snap: Snapshot, key: str | None) -> bool:
    """Whether the container ``key`` (``None``: the snapshot itself) was read in full in ``snap``."""
    return key is None or (key in snap and snap[key].value.startswith(READ))


def compared(before: Snapshot, after: Snapshot, key: str) -> bool:
    """Whether ``key`` compares as a steering file: present at both ends, or (not a container) absent at one where
    what lists it was read in full. Otherwise its absence is a gap in what that end could see (a hooks directory
    unreadable or over the cap, a config file unreadable, a hooks directory no longer the one the config names),
    not a change: that container's own ``check_error``, or the config change, reports it. A container present at
    both ends compares by its value (a ``.git`` leading elsewhere)."""
    b, a = before.get(key), after.get(key)
    e = a or b
    if e is None:
        return False
    if any(x and x.value.startswith(READ) for x in (b, a)):
        return b is not None and a is not None
    return (b is not None or _read(before, e.parent)) and (a is not None or _read(after, e.parent))


def _unresolved(name: Path) -> str | None:
    """Why git could not follow ``name`` as far as it exists, else ``None``: the deepest part of it that exists (the
    name itself, or a directory above it) must resolve. A link there that is dangling, a loop or unreadable is a
    path git cannot read, never a file that is absent."""
    part = next(a for a in (name, *name.parents) if os.path.lexists(a))
    return None if os.path.exists(part) else f"{part} does not resolve (a dangling link, a loop or no access)"


def _link(snap: Snapshot, scope: Scope, name: Path, cls: str, parent: str,
          values: tuple[tuple[str, str], ...] = ()) -> Path | None:
    """The real path ``name`` resolves to. When that is not ``name`` itself (a symlink on the way), ``name`` is also
    recorded, keyed by its normalized absolute path, as ``link:<real path>`` (with the watched ``values`` of what it
    leads to), so creating, removing or retargeting the link compares. A name git cannot follow (:func:`_unresolved`:
    a dangling or looping link, the name's own or a directory's above it) is recorded as unreadable and ``None``
    returned: the module's one rule."""
    real, key = resolved_path(name), os.path.abspath(name)
    why = _unresolved(Path(key))
    if why is None and key == str(real):
        return real
    value = _error(FileNotFoundError(why)) if why else f"link:{real}"
    snap.setdefault(key, Entry(scope.display(Path(key)), cls, value, () if why else values, parent))
    return None if why else real


def _add_hook(snap: Snapshot, scope: Scope, path: Path, parent: str) -> None:
    """Record one hooks-directory entry once (by its real path), read under the one rule."""
    real = real_path(path)
    if str(real) in snap:
        return
    try:
        _in_time()
        value = _hook_value(path)
    except Exception as e:  # noqa: BLE001 — one rule: an unreadable input is reported, never fatal
        value = _error(e)
    if value is not None:
        snap[str(real)] = Entry(scope.display(real), "git_hook", value, parent=parent)


def _hooks_dir(snap: Snapshot, scope: Scope, name: Path, parent: str) -> None:
    """Direct entries of the hooks directory ``name`` resolves to (:func:`_link`; listed once), not recursive; over
    :data:`HOOKS_CAP` the directory itself is unreadable (so every comparison fails closed), and the listing stops
    after ``HOOKS_CAP + 1`` entries. A directory that does not exist is read in full: empty."""
    d = _link(snap, scope, name, "git_hook", parent)
    if d is None or str(d) in snap:
        return
    key = str(d)

    def each() -> None:
        if not os.path.lexists(d):
            snap[key] = Entry(scope.display(Path(key)), "git_hook", READ + "dir")
            return
        with os.scandir(d) as it:
            names = [e.name for e in itertools.islice(it, HOOKS_CAP + 1)]
        if len(names) > HOOKS_CAP:
            raise OSError(f"hooks directory has more than {HOOKS_CAP} entries")
        snap[key] = Entry(scope.display(Path(key)), "git_hook", READ + "dir")
        for name in sorted(names):
            _add_hook(snap, scope, d / name, key)
    guarded(snap, scope, d, "git_hook", each)


def _config_file(snap: Snapshot, scope: Scope, top: Path, start: Path, dotgit: str,
                 hooks: dict[Path | None, bool]) -> None:
    """One config file git reads and those it includes, each guarded and keyed by the file it resolves to (one
    file reached by two names is one entry); each ``core.hooksPath`` value goes to ``hooks`` with whether only an
    ``includeIf`` named it."""
    for f in read_chain(start, parse_bytes):
        parent = str(resolved_path(f.parent)) if f.parent else dotgit
        values = () if isinstance(f.data, Exception) else tuple(sorted(watched_values(f.pairs).items()))
        real = _link(snap, scope, f.path, "git_config", parent, values)
        if real is None:
            continue
        if isinstance(f.data, FileNotFoundError):   # recorded, so its creation compares under an unchanged includer
            snap.setdefault(str(real), Entry(scope.display(real), "git_config", ABSENT, parent=parent))
            continue
        if isinstance(f.data, Exception):
            unreadable(snap, scope, real, "git_config", f.data)
            continue
        snap.setdefault(str(real), Entry(scope.display(real), "git_config", hashlib.sha256(f.data).hexdigest(),
                                         values, parent))
        for k, v in f.pairs:
            if k == "core.hookspath":   # an empty value is set too: it names no directory (None)
                d = top / os.path.expanduser(v) if v else None
                hooks[d] = hooks.get(d, True) and f.conditional


def git_snapshot(scope: Scope) -> Snapshot:
    """Git steering, from the filesystem only: per checkout, the common ``config``, ``config.worktree`` and every
    file they name by ``include.path`` or ``includeIf.*.path`` (:mod:`specy_road.git_config_text`, conditions not
    evaluated), and the hooks directories: ``core.hooksPath`` when set (each value read, relative to the checkout),
    else ``<common>/hooks`` and ``<worktree-gitdir>/hooks``. A value only an ``includeIf`` names may not apply (its
    condition is not evaluated), so with no other value the default directories are watched as well. An empty
    ``core.hooksPath`` is a value too: it names no directory, and turns the defaults off as any other value does
    (git then runs no hook git dir or checkout holds; git 2.43 looks for ``/<hook>``, which only root can write)."""
    global _until
    snap: Snapshot = {}
    _until = time.monotonic() + SNAPSHOT_SECONDS
    try:
        for top in scope.tops:
            guarded(snap, scope, top / ".git", "git_config", lambda top=top: _git_top(snap, scope, top))
    finally:
        _until = float("inf")
    return snap


def _git_top(snap: Snapshot, scope: Scope, top: Path) -> None:
    gitdir, common = _gitdirs(top)
    dotgit = real_path(top / ".git")   # where it leads is its value: a .git retargeted is a change of it
    snap[str(dotgit)] = Entry(scope.display(dotgit), "git_config", f"{READ}gitdir {gitdir} common {common}")
    hooks: dict[Path | None, bool] = {}   # each core.hooksPath directory (None: empty): whether only an includeIf named it
    for start in dict.fromkeys((common / "config", common / "config.worktree", gitdir / "config.worktree")):
        _config_file(snap, scope, top, start, str(dotgit), hooks)
    default = [common / "hooks", gitdir / "hooks"] if all(hooks.values()) else []
    for d in dict.fromkeys([*filter(None, hooks), *default]):
        _hooks_dir(snap, scope, d, str(dotgit))
