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

Writes and moves go by directory descriptor: the root is opened once and each
directory below it with ``O_NOFOLLOW`` relative to the one above, so a link
swapped in after the check fails the open. The temp file is created exclusively
in the held parent and replaced there; right before the replace every held
directory's identity is compared with an ``lstat`` of its path, so a swap is
refused, and one after that comparison can only land in the directory walked.
Where ``os.supports_dir_fd`` lacks ``os.open`` or ``os.rename`` (Windows), the
destination and parent are checked again with ``lstat`` right before ``os.replace``.
"""

from __future__ import annotations

import ast
import contextlib
import errno
import os
import secrets
import shutil
import stat
import sys
from pathlib import Path

FILE = "a regular file"
DIRECTORY = "a directory"
_ENTRY = "a regular file or a symlink"

#: What a path is, by ``lstat`` mode; the first match names it.
_KINDS = ((stat.S_ISLNK, "a symlink"), (stat.S_ISDIR, DIRECTORY), (stat.S_ISREG, FILE),
          (stat.S_ISFIFO, "a FIFO"), (stat.S_ISSOCK, "a socket"), (stat.S_ISCHR, "a device"), (stat.S_ISBLK, "a device"))


class SafeWriteError(OSError):
    """A path the safe-write rule refuses; ``str()`` is the one-line reason."""


def _kind(path: Path, expected: str, dir_fd: int | None = None) -> str | None:
    """``path``'s kind by ``lstat`` (its name in ``dir_fd`` when given), or ``None`` when it is absent."""
    try:
        mode = (os.lstat(path) if dir_fd is None else os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)).st_mode
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


def check_all(root: Path, paths, expected: str | None = FILE) -> None:
    """:func:`check` each of ``paths``; the first refusal raises, so a caller can stop before its first write."""
    for path in paths:
        check(root, path, expected)


def _loops(path: Path) -> bool:
    try:
        os.stat(path)
    except OSError as e:
        return e.errno == errno.ELOOP
    return False


def loop_refusal(e: BaseException) -> SafeWriteError | None:
    """``e`` as the rule's refusal: itself for a :class:`SafeWriteError`; for a symlink loop that code reading,
    resolving or making a directory met before the rule did, the refusal of the looping link; else ``None``.

    A loop shows as ``ELOOP``, as pathlib's ``RuntimeError("Symlink loop from ...")``
    (``resolve()`` before Python 3.13), or as ``FileExistsError`` from ``mkdir``
    over a looping link. The looping link is the shallowest component of the
    error's path that is a symlink ``stat`` cannot follow.
    """
    if isinstance(e, SafeWriteError):
        return e
    if isinstance(e, RuntimeError) and str(e).startswith("Symlink loop from "):
        name = ast.literal_eval(str(e).removeprefix("Symlink loop from "))
    elif isinstance(e, OSError) and e.errno in (errno.ELOOP, errno.EEXIST) and e.filename:
        name = e.filename
    else:
        return None
    full = Path(os.fsdecode(name))
    here = Path(full.anchor)
    for part in full.parts[1:]:
        here = here / part
        if os.path.islink(here) and _loops(here):
            return _refusal(here, "a symlink", DIRECTORY if here != full else f"{FILE} or {DIRECTORY}")
    return None


def refusal_of(e: OSError | RuntimeError) -> SafeWriteError:
    """:func:`loop_refusal` of ``e``; ``e`` itself is raised again when it is neither a refusal nor a loop."""
    refusal = loop_refusal(e)
    if refusal is None:
        raise e
    return refusal


@contextlib.contextmanager
def exit_on_refusal():
    """The command-line boundary: a :class:`SafeWriteError`, or a symlink loop (:func:`loop_refusal`), inside
    prints ``error: <message>`` on stderr and exits 1, no traceback."""
    try:
        yield
    except (OSError, RuntimeError) as e:
        print(f"error: {refusal_of(e)}", file=sys.stderr)
        raise SystemExit(1) from e


def refused(root: Path, path: Path | str, expected: str | None = FILE) -> str | None:
    """:func:`check`'s refusal as one line, or ``None`` when the rule allows ``path``."""
    try:
        check(root, path, expected)
    except SafeWriteError as e:
        return str(e)
    return None


def _dir_fds() -> bool:
    """Whether this platform walks and replaces by directory descriptor (not Windows); ``os.replace`` takes
    descriptors where ``os.rename`` does (``renameat``), and only ``os.rename`` is listed."""
    return hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW") and {
        os.open, os.rename, os.stat, os.mkdir, os.unlink} <= os.supports_dir_fd


@contextlib.contextmanager
def _held(base: Path, parts: tuple[str, ...], create: bool):
    """Open ``base``, then each directory of ``parts`` without following a link, relative to the one above
    (made first when ``create``); yields ``[(path, descriptor), ...]`` from the root down, all held open."""
    held: list[tuple[Path, int]] = []
    try:
        held.append((base, os.open(base, os.O_RDONLY | os.O_DIRECTORY)))
        for name in parts:
            here, parent = held[-1][0] / name, held[-1][1]
            if create:
                with contextlib.suppress(FileExistsError):
                    os.mkdir(name, dir_fd=parent)
            try:
                held.append((here, os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)))
            except OSError:
                kind = _kind(here, DIRECTORY, parent)
                if kind in (None, DIRECTORY):
                    raise
                raise _refusal(here, kind, DIRECTORY) from None
        yield held
    finally:
        for _path, fd in held:
            os.close(fd)


def mkdirs(root: Path, d: Path | str) -> Path:
    """Create ``d`` and its missing parents; an existing real directory is fine.

    A missing root is created too: nothing at or above it is inspected.
    """
    base, parts = _locate(root, d)
    base.mkdir(parents=True, exist_ok=True)
    if _dir_fds():
        with _held(base, parts, create=True):
            return base.joinpath(*parts)
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


def _recheck(full: Path, held: list[tuple[Path, int]] | None = None) -> None:
    """Right before replace: each ``held`` directory is still the one walked (without, the parent is a real
    directory by ``lstat``), and ``full`` absent or a regular file."""
    for path, fd in held or [(full.parent, None)]:
        kind = _kind(path, DIRECTORY)
        if kind != DIRECTORY:
            raise _refusal(path, kind or "absent", DIRECTORY)
        if fd is not None and not os.path.samestat(os.lstat(path), os.fstat(fd)):
            raise SafeWriteError(f"{path} is a different directory, not the one walked")
    kind = _kind(full, FILE, held[-1][1] if held else None)
    if kind not in (None, FILE):
        raise _refusal(full, kind, FILE)


def _temp(parent: Path, name: str, dir_fd: int | None = None) -> tuple[int, Path]:
    """A new file created exclusively in ``parent`` (its descriptor ``dir_fd`` when given), mode ``0o666``
    less the umask (as ``write_text`` makes)."""
    while True:
        tmp = parent / f".{name}.{secrets.token_hex(6)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            return os.open(tmp if dir_fd is None else tmp.name, flags, 0o666, dir_fd=dir_fd), tmp
        except FileExistsError:
            continue


def _old_mode(full: Path, dir_fd: int | None = None) -> int | None:
    """``full``'s mode when it is a regular file, so a rewrite keeps it."""
    if _kind(full, FILE, dir_fd) != FILE:
        return None
    return (os.lstat(full) if dir_fd is None else os.stat(full.name, dir_fd=dir_fd, follow_symlinks=False)).st_mode


def _replace(root: Path, path: Path | str, data: bytes, finish) -> Path:
    full = check(root, path, FILE)
    if not _dir_fds():   # M21.37's lstat re-check right before replace
        mkdirs(root, full.parent)
        fd, tmp = _temp(full.parent, full.name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            finish(tmp, _old_mode(full))
            _recheck(full)
            os.replace(tmp, full)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return full
    base, parts = _locate(root, full)
    base.mkdir(parents=True, exist_ok=True)
    with _held(base, parts[:-1], create=True) as held:
        parent = held[-1][1]
        fd, tmp = _temp(full.parent, full.name, parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            try:
                finish(tmp, _old_mode(full, parent))
            except OSError:
                _recheck(full, held)   # a directory swapped under the temp file's path: name it
                raise
            _recheck(full, held)
            os.replace(tmp.name, full.name, src_dir_fd=parent, dst_dir_fd=parent)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp.name, dir_fd=parent)
            raise
    return full


def _keep_mode(mode: int | None):
    def finish(tmp: Path, old: int | None) -> None:
        if mode is not None:
            os.chmod(tmp, mode)
        elif old is not None:   # a rewrite keeps the file's mode
            os.chmod(tmp, stat.S_IMODE(old))
    return finish


def write(root: Path, path: Path | str, data: str | bytes, mode: int | None = None) -> Path:
    """Atomically replace ``path`` with ``data`` (``str`` is UTF-8); missing parents are made by :func:`mkdirs`.

    ``mode`` defaults to the existing file's, or the umask's for a new file.
    """
    return _replace(root, path, data.encode("utf-8") if isinstance(data, str) else data, _keep_mode(mode))


def copy(root: Path, src: Path | str, dst: Path | str) -> Path:
    """:func:`write` ``src``'s bytes to ``dst``, keeping its mode and times (as ``shutil.copy2``)."""
    return _replace(root, dst, Path(src).read_bytes(), lambda tmp, _old: shutil.copystat(src, tmp))


def move(root: Path, src: Path | str, dst: Path | str) -> Path:
    """Rename the regular file ``src`` to ``dst`` (absent or a regular file), each reached as spelled under
    ``root`` by the rule; missing parents of ``dst`` are made by :func:`mkdirs`."""
    source, target = check(root, src, FILE), check(root, dst, FILE)
    if not _dir_fds():   # M21.37's lstat re-check right before replace
        mkdirs(root, target.parent)
        _recheck(source)
        _recheck(target)
        os.replace(source, target)
        return target
    base, parts = _locate(root, source)
    with _held(base, parts[:-1], create=False) as froms, _held(base, _locate(root, target)[1][:-1], True) as tos:
        _recheck(source, froms)
        _recheck(target, tos)
        os.replace(source.name, target.name, src_dir_fd=froms[-1][1], dst_dir_fd=tos[-1][1])
    return target


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
