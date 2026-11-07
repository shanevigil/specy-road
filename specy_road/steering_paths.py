"""Steering files: what an executor can write that trusted code outside it later reads or runs (M21.7).

An unattended executor works in a linked worktree, and some files it can write are read or run later by
something it does not control: git reads hooks and ``core.fsmonitor`` / ``core.hooksPath`` from the common git
dir, which every worktree of the repository shares. This module holds the one list (documented in
docs/orchestration-steering-files.md, linked from docs/orchestration-workers.md) and the per-turn watch:

- the snapshot (:func:`git_snapshot`) that the post-run check
  (:class:`~specy_road.worker_turn_check.SteeringWatch`) takes per worker turn, in the worktree and in the main
  checkout, and compares as ``steering_file`` findings. It is read from the filesystem only, so it is
  compared before any post-turn git command runs.

Detection only: nothing here restores a changed file. Paths compare project-relative, as ``zone_matches``
does, and one real path is stored once.

**One rule for any input that cannot be read** (:func:`guarded`): every per-file and per-directory step (listing,
reading, decoding, parsing, hashing) runs on its own, and any exception there (invalid UTF-8, a permission error,
a dangling link or a link loop, a file over :data:`MAX_PARSE_BYTES`, a file gone mid-read) records
that path and its class as unreadable (an ``error:`` value) and the snapshot goes on with every other path. The
comparison reports each such path as a ``check_error`` finding (path and class) and never as unchanged; it
counts as git steering not verified, so no post-turn git command runs. Only a path that does not
exist is ``absent``.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from specy_road.git_config_text import git_reads, read_chain, watched_values
from specy_road.runtime_paths import prefix_within
from specy_road.worktree_env import git_top, main_project_root

#: The sticky worker flag a ``steering_file`` finding sets; only ``worker reconcile`` (without ``--dismiss``) clears it.
FLAG_STEERING = "steering_changed"
#: Every ``class`` a ``steering_file`` finding can carry.
CLASSES = ("git_hook", "git_config")
#: More direct children than this in a hooks directory are recorded as the one marker ``capped``.
HOOKS_CAP = 200
ABSENT = "absent"
#: The prefix of a value that could not be read (:func:`guarded`).
ERROR = "error:"
#: Files this module parses (``.git`` files, git config) larger than this are unreadable, not parsed.
MAX_PARSE_BYTES = 8 * 1024 * 1024


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(path: Path) -> str:
    """A file's sha256, streamed: size is never a reason to fail."""
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def parse_bytes(path: Path) -> bytes:
    """A file this module parses, refused over :data:`MAX_PARSE_BYTES`."""
    with open(path, "rb") as f:
        data = f.read(MAX_PARSE_BYTES + 1)
    if len(data) > MAX_PARSE_BYTES:
        raise ValueError(f"over the {MAX_PARSE_BYTES} byte parse cap")
    return data


def resolved_path(path: Path) -> Path:
    """``path`` resolved without raising: a link loop or a missing part (an executor can make either) stays as named."""
    return Path(os.path.realpath(path))


def _value(path: Path) -> str:
    """A path's content as every class compares it: a file's sha256; ``link:<text>`` plus ``@<sha256>`` of what a
    link resolves to when that is a regular file (a write through an unchanged link changes it; a link to a
    directory is not walked); ``dir``; ``other``; ``absent`` when nothing is there. Raises when the content cannot
    be read (a dangling link or a loop included): :func:`guarded` records that."""
    if not os.path.lexists(path):
        return ABSENT
    if path.is_symlink():
        text, mode = os.readlink(path), os.stat(path).st_mode   # stat follows: a dangling link or a loop raises
        return f"link:{text}" + (f"@{_digest(path)}" if stat.S_ISREG(mode) else "")
    mode = os.stat(path).st_mode
    return _digest(path) if stat.S_ISREG(mode) else "dir" if stat.S_ISDIR(mode) else "other"


def real_path(path: Path) -> Path:
    """``path`` with its parent resolved and its last component kept: a link is recorded, not followed."""
    return Path(os.path.realpath(path.parent)) / path.name


@dataclass(frozen=True)
class Entry:
    path: str                 # as findings name it: project-relative in the worker's tree, else absolute
    cls: str
    value: str
    values: tuple[tuple[str, str], ...] = ()   # git_config only: the watched keys' values


Snapshot = dict[str, Entry]   # keyed by the real path


def _gitdirs(top: Path) -> tuple[Path, Path] | None:
    """``(worktree gitdir, common git dir)`` of the checkout at ``top``, read from ``.git`` without running git."""
    dotgit = top / ".git"
    if dotgit.is_dir():
        return resolved_path(dotgit), resolved_path(dotgit)
    if not dotgit.exists():
        return None
    line = parse_bytes(dotgit).decode("utf-8").strip()
    if not line.startswith("gitdir:"):
        return None
    gitdir = resolved_path(top / line.removeprefix("gitdir:").strip())
    commondir = gitdir / "commondir"
    common = resolved_path(gitdir / parse_bytes(commondir).decode("utf-8").strip()) if commondir.exists() else gitdir
    return gitdir, common


@dataclass(frozen=True)
class Scope:
    """Where one worker's steering files live: its worktree and the main checkout, the same project prefix."""
    prefix: str
    w_top: Path
    m_top: Path
    #: per checkout top, what git itself said it reads at the turn's start (:func:`git_reads`)
    git_known: dict[Path, tuple[list[Path], list[Path]]] = field(default_factory=dict, compare=False)

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
    """The worker's scope, taken at the turn's start: the only time git is asked what it reads."""
    m_root = resolved_path(main_project_root(Path(repo_root)))
    m_top, w_top = git_top(m_root), git_top(Path(worktree))
    return Scope(prefix_within(m_top, m_root), w_top, m_top,
                 {top: git_reads(top) for top in dict.fromkeys((w_top, m_top))})


def guarded(snap: Snapshot, scope: Scope, path: Path, cls: str, step: Callable[[], None]) -> None:
    """Run one per-file or per-directory ``step``; any exception records ``path`` as unreadable for ``cls``
    (the module's one rule) and the snapshot goes on."""
    try:
        step()
    except Exception as e:  # noqa: BLE001 — one rule: an unreadable input is reported, never fatal
        unreadable(snap, scope, path, cls, e)


def unreadable(snap: Snapshot, scope: Scope, path: Path, cls: str, e: BaseException) -> None:
    """Record ``path`` as unreadable for ``cls``, replacing whatever was recorded for it."""
    real = real_path(path)
    snap[str(real)] = Entry(scope.display(real), cls, _error(e))


def _add(snap: Snapshot, scope: Scope, path: Path, cls: str, value: str | None = None) -> None:
    """Record one path once (by its real path), its value read under the one rule: unreadable is an ``error:``."""
    real = real_path(path)
    if str(real) in snap:
        return
    try:
        value = value if value is not None else _value(path)
    except Exception as e:  # noqa: BLE001 — one rule: an unreadable input is reported, never fatal
        value = _error(e)
    snap[str(real)] = Entry(scope.display(real), cls, value)


def _list(snap: Snapshot, scope: Scope, d: Path, cls: str, each: Callable[[list[Path]], None]) -> None:
    """``each`` on the sorted entries of directory ``d`` (none when it does not exist), guarded."""
    if os.path.lexists(d):
        guarded(snap, scope, d, cls, lambda: each(sorted(d.iterdir())))


def _hooks_dir(snap: Snapshot, scope: Scope, d: Path) -> None:
    def each(kids: list[Path]) -> None:
        if len(kids) > HOOKS_CAP:
            _add(snap, scope, d, "git_hook", "capped")
            return
        for k in kids:
            if not k.is_dir() or k.is_symlink():   # direct entries; a real subdirectory is not a hook
                _add(snap, scope, k, "git_hook")
    _list(snap, scope, d, "git_hook", each)


def _config_file(snap: Snapshot, scope: Scope, top: Path, start: Path, hooks: list[Path]) -> None:
    """One config file git reads and those it includes, each guarded; their ``core.hooksPath`` values go to ``hooks``."""
    for path, data, pairs in read_chain(start, parse_bytes):
        if isinstance(data, Exception):
            unreadable(snap, scope, path, "git_config", data)
            continue
        real = real_path(path)
        snap.setdefault(str(real), Entry(scope.display(real), "git_config", _sha(data),
                                         tuple(sorted(watched_values(pairs).items()))))
        hooks += [top / os.path.expanduser(v) for k, v in pairs if k == "core.hookspath" and v]


def git_snapshot(scope: Scope) -> Snapshot:
    """Git steering, from the filesystem only: the config files and hooks directories git named at the turn's
    start (``scope.git_known``), plus, as candidates from :mod:`specy_road.git_config_text`, the common
    ``config``, ``config.worktree`` and every file they include (conditions not evaluated), ``<common>/hooks``,
    ``<worktree-gitdir>/hooks`` and each ``core.hooksPath`` value read (relative to the checkout)."""
    snap: Snapshot = {}
    for top in scope.tops:
        guarded(snap, scope, top / ".git", "git_config", lambda top=top: _git_top(snap, scope, top))
    return snap


def _git_top(snap: Snapshot, scope: Scope, top: Path) -> None:
    known_hooks, known_files = scope.git_known.get(top, ([], []))
    hooks, starts = list(known_hooks), list(known_files)
    if dirs := _gitdirs(top):
        gitdir, common = dirs
        hooks += [common / "hooks", gitdir / "hooks"]
        starts += [common / "config", common / "config.worktree", gitdir / "config.worktree"]
    for start in dict.fromkeys(starts):
        _config_file(snap, scope, top, start, hooks)
    for d in dict.fromkeys(resolved_path(h) for h in hooks):
        _hooks_dir(snap, scope, d)
