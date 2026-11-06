"""One safe-write rule for every path specy-road creates, rewrites or deletes in a tree it owns.

Before any mkdir, write or delete, walk with ``lstat`` from the owned root
(resolved once; nothing above it is inspected) to the destination. Every
ancestor below the root must be a real directory, so a symlink there (dangling,
in the repository or out of it), a non-directory where a directory belongs, and
a lexical ``..`` that leaves the root are all refused with :class:`SafeWriteError`.

What the final component may be depends on the operation:

========================  ==================================================
``write``, ``copy``       absent or a regular file
``open_lock``             absent or a regular file
``mkdirs``                absent or a real directory
``remove``                a regular file, or a symlink unlinked as an entry
``prune_empty``           a real directory by ``lstat`` (a link stops it)
========================  ==================================================

A refusal reads ``"<path> is <kind>, not <expected>"``, with ``(to <readlink>)``
after ``a symlink``: the sentence finish's ``irregular_destination`` uses.

Writes are atomic: a temp file is created exclusively in the verified parent,
and the destination and parent are checked again with ``lstat`` right before
``os.replace``. Descriptor-anchored traversal (``openat`` per component) would
close the remaining race; it is not done here.
"""

from __future__ import annotations

import os
import secrets
import shutil
import stat
from pathlib import Path

FILE = "a regular file"
DIRECTORY = "a directory"
_ENTRY = "a regular file or a symlink"

#: What a path is, by ``lstat`` mode; the first match names it.
_KINDS = ((stat.S_ISLNK, "a symlink"), (stat.S_ISDIR, DIRECTORY), (stat.S_ISREG, FILE),
          (stat.S_ISFIFO, "a FIFO"), (stat.S_ISSOCK, "a socket"), (stat.S_ISCHR, "a device"), (stat.S_ISBLK, "a device"))


class SafeWriteError(OSError):
    """A path the safe-write rule refuses; ``str()`` is the one-line reason."""


def _kind(path: Path, expected: str) -> str | None:
    """``path``'s kind by ``lstat``, or ``None`` when it is absent."""
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return None
    except OSError as e:
        raise SafeWriteError(f"{path} cannot be inspected ({e.strerror or e}), not {expected}") from e
    return next((name for test, name in _KINDS if test(mode)), "an unknown file type")


def _refusal(path: Path, kind: str, expected: str) -> SafeWriteError:
    link = ""
    if kind == "a symlink":
        try:
            link = f" (to {os.readlink(path)})"
        except OSError:
            link = ""
    return SafeWriteError(f"{path} is {kind}{link}, not {expected}")


def _below(anchor: Path, full: Path) -> tuple[str, ...] | None:
    """The parts of ``full`` below ``anchor``, with ``.`` and ``..`` applied in order; ``None`` when it is not
    spelled from ``anchor`` or a ``..`` climbs above it at any step (re-entering afterwards does not count)."""
    head = len(anchor.parts)
    if full.parts[:head] != anchor.parts:
        return None
    parts: list[str] = []
    for name in full.parts[head:]:
        if name == "..":
            if not parts:
                return None
            parts.pop()
        elif name != ".":
            parts.append(name)
    return tuple(parts)


def _locate(root: Path, path: Path | str) -> tuple[Path, tuple[str, ...]]:
    """``(resolved root, parts below it)`` for ``path``, taken lexically.

    A relative ``path`` is under ``root``; an absolute one must be spelled from
    ``root`` as given, normalized or resolved. A ``..`` that climbs above the
    root at any step is refused, even when a later part comes back in.
    """
    base = Path(root).resolve()
    full = Path(path) if Path(path).is_absolute() else Path(root, path)
    full = full if full.is_absolute() else Path.cwd() / full
    for anchor in (Path(root).absolute(), Path(os.path.normpath(Path(root).absolute())), base):
        parts = _below(anchor, full)
        if parts is not None:
            return base, parts
    raise SafeWriteError(f"{full} is outside {base}, not a path under it")


def _walk(root: Path, path: Path | str, expected: str | None) -> tuple[Path, str | None]:
    """Check every ancestor of ``path`` below ``root``; return ``(path from the resolved root, final kind)``.

    ``expected`` is the final kinds allowed besides absent; ``None`` allows any.
    """
    base, parts = _locate(root, path)
    here = base
    for name in parts[:-1]:
        here = here / name
        kind = _kind(here, DIRECTORY)
        if kind is None:
            return base.joinpath(*parts), None
        if kind != DIRECTORY:
            raise _refusal(here, kind, DIRECTORY)
    full = base.joinpath(*parts)
    kind = _kind(full, expected or DIRECTORY)
    if kind is not None and expected is not None and kind not in expected.split(" or "):
        raise _refusal(full, kind, expected)
    return full, kind


def check(root: Path, path: Path | str, expected: str | None = FILE) -> Path:
    """Refuse ``path`` unless the rule allows it with a final component absent or ``expected``.

    ``expected`` is :data:`FILE` (default), :data:`DIRECTORY`, or ``None`` for
    any final kind (ancestors only). Returns the path spelled from the resolved root.
    """
    return _walk(root, path, expected)[0]


def mkdirs(root: Path, d: Path | str) -> Path:
    """Create ``d`` and its missing parents; an existing real directory is fine.

    A missing root is created too: nothing at or above it is inspected.
    """
    base, parts = _locate(root, d)
    base.mkdir(parents=True, exist_ok=True)
    here = base
    for name in parts:
        here = here / name
        kind = _kind(here, DIRECTORY)
        if kind is None:
            try:
                os.mkdir(here)
            except FileExistsError:
                kind = _kind(here, DIRECTORY)
            else:
                kind = DIRECTORY
        if kind != DIRECTORY:
            raise _refusal(here, kind or "absent", DIRECTORY)
    return here


def _recheck(full: Path) -> None:
    """The parent is still a real directory and ``full`` absent or a regular file, right before replace."""
    parent = _kind(full.parent, DIRECTORY)
    if parent != DIRECTORY:
        raise _refusal(full.parent, parent or "absent", DIRECTORY)
    kind = _kind(full, FILE)
    if kind not in (None, FILE):
        raise _refusal(full, kind, FILE)


def _temp(parent: Path, name: str) -> tuple[int, Path]:
    """A new file created exclusively in ``parent``, mode ``0o666`` less the umask (as ``write_text`` makes)."""
    while True:
        tmp = parent / f".{name}.{secrets.token_hex(6)}.tmp"
        try:
            return os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o666), tmp
        except FileExistsError:
            continue


def _replace(root: Path, path: Path | str, data: bytes, finish) -> Path:
    full = check(root, path, FILE)
    mkdirs(root, full.parent)
    fd, tmp = _temp(full.parent, full.name)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        finish(tmp, full)
        _recheck(full)
        os.replace(tmp, full)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return full


def _keep_mode(mode: int | None):
    def finish(tmp: Path, full: Path) -> None:
        if mode is not None:
            os.chmod(tmp, mode)
        elif _kind(full, FILE) == FILE:   # a rewrite keeps the file's mode
            os.chmod(tmp, stat.S_IMODE(os.lstat(full).st_mode))
    return finish


def write(root: Path, path: Path | str, data: str | bytes, mode: int | None = None) -> Path:
    """Atomically replace ``path`` with ``data`` (``str`` is UTF-8); missing parents are made by :func:`mkdirs`.

    ``mode`` defaults to the existing file's, or the umask's for a new file.
    """
    return _replace(root, path, data.encode("utf-8") if isinstance(data, str) else data, _keep_mode(mode))


def copy(root: Path, src: Path | str, dst: Path | str) -> Path:
    """:func:`write` ``src``'s bytes to ``dst``, keeping its mode and times (as ``shutil.copy2``)."""
    return _replace(root, dst, Path(src).read_bytes(), lambda tmp, _full: shutil.copystat(src, tmp))


def remove(root: Path, path: Path | str) -> bool:
    """Unlink a regular file or a symlink entry (never followed); whether something was removed."""
    full, kind = _walk(root, path, _ENTRY)
    if kind is None:
        return False
    os.unlink(full)
    return True


def prune_empty(root: Path, d: Path | str) -> None:
    """``rmdir`` ``d`` and then each parent below ``root`` while it is an empty real directory.

    Stops at the first that is absent, not empty, or not a real directory by
    ``lstat``: a symlinked directory is never listed or removed.
    """
    base, parts = _locate(root, d)
    while parts:
        full, kind = _walk(base, base.joinpath(*parts), None)
        if kind != DIRECTORY or os.listdir(full):
            return
        os.rmdir(full)
        parts = parts[:-1]


def open_lock(root: Path, path: Path | str, flags: int = os.O_RDWR | os.O_CREAT, mode: int = 0o644) -> int:
    """Open ``path`` (absent or a regular file) without following a final link; returns the descriptor."""
    full = check(root, path, FILE)   # where O_NOFOLLOW is absent (Windows) this lstat refusal is the guard
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(full, flags | nofollow, mode)
    except OSError:
        check(root, full, FILE)   # a link swapped in: name it
        raise
