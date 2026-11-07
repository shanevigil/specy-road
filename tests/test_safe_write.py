"""M21.37: the one safe-write rule, per operation (specy_road/safe_write.py)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from specy_road import safe_write
from specy_road.generated_files import regenerate_generated_files
from specy_road.init_project import run_init_project
from specy_road.managed_block import apply_managed_block
from specy_road.safe_write import SafeWriteError

OLD = b"old\n"


def _place(kind: str, path: Path, outside: Path) -> None:
    """Put ``kind`` at ``path``: absent, a regular file, a directory, a FIFO, or a symlink (in, out, dangling)."""
    if kind == "file":
        path.write_bytes(OLD)
    elif kind == "dir":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "link_in":
        path.with_name("inner").write_bytes(OLD)
        path.symlink_to("inner")
    elif kind == "link_out":
        (outside / "theirs").write_bytes(OLD)
        path.symlink_to(outside / "theirs")
    elif kind == "dangling":
        path.symlink_to(outside / "made")


KINDS = ("absent", "file", "dir", "fifo", "link_in", "link_out", "dangling")


def _write(root: Path, path: Path) -> None:
    safe_write.write(root, path, "new\n")


def _copy(root: Path, path: Path) -> None:
    src = root.parent / "src"
    src.write_bytes(b"new\n")
    safe_write.copy(root, src, path)


def _lock(root: Path, path: Path) -> None:
    os.close(safe_write.open_lock(root, path))


# operation -> (call, final kinds it allows)
OPERATIONS = {
    "write": (_write, {"absent", "file"}),
    "copy": (_copy, {"absent", "file"}),
    "open_lock": (_lock, {"absent", "file"}),
    "mkdirs": (lambda root, path: safe_write.mkdirs(root, path), {"absent", "dir"}),
    "remove": (lambda root, path: safe_write.remove(root, path), {"absent", "file", "link_in", "link_out", "dangling"}),
}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs here")
@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("operation", list(OPERATIONS))
def test_each_operation_allows_only_its_final_kinds(tmp_path: Path, operation: str, kind: str) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    path = root / "x"
    _place(kind, path, outside)
    theirs = {p: p.read_bytes() for p in outside.iterdir()}
    call, allowed = OPERATIONS[operation]

    if kind not in allowed:
        with pytest.raises(SafeWriteError, match=f"^{path} is a"):
            call(root, path)
        assert os.path.lexists(path) and not (kind == "dangling" and (outside / "made").exists())
    else:
        call(root, path)
        if operation in ("write", "copy"):
            assert path.read_bytes() == b"new\n" and not path.is_symlink()
        elif operation == "mkdirs":
            assert path.is_dir()
        elif operation == "remove":
            assert not os.path.lexists(path)
    assert {p: p.read_bytes() for p in outside.iterdir()} == theirs   # a symlink orphan's target stays
    if kind == "link_in":
        assert (root / "inner").read_bytes() == OLD


@pytest.mark.parametrize("kind", ["link_in", "link_out", "dangling", "file"])
@pytest.mark.parametrize("operation", list(OPERATIONS))
def test_an_ancestor_must_be_a_real_directory(tmp_path: Path, operation: str, kind: str) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "inner").mkdir()
    (outside / "theirs").mkdir()
    sub = root / "sub"
    if kind == "file":
        sub.write_bytes(OLD)
    else:
        sub.symlink_to({"link_in": root / "inner", "link_out": outside / "theirs", "dangling": outside / "made"}[kind])
    expected = "a regular file" if kind == "file" else "a symlink"

    with pytest.raises(SafeWriteError, match=f"^{sub} is {expected}.*, not a directory$"):
        OPERATIONS[operation][0](root, sub / "x")
    assert not any((root / "inner").iterdir()) and not any((outside / "theirs").iterdir())
    assert not (outside / "made").exists()


def test_dot_dot_out_of_the_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(SafeWriteError, match="is outside .*, not a path under it"):
        safe_write.write(root, root / ".." / "escaped", "x")
    assert not (tmp_path / "escaped").exists()
    for reentering in ("../root/back", root / "a" / ".." / ".." / "root" / "back"):   # climbing above counts
        with pytest.raises(SafeWriteError, match="is outside .*, not a path under it"):
            safe_write.write(root, reentering, "x")
    assert not (root / "back").exists()
    safe_write.write(root, "a/../b", "x")   # lexical, and never above the root: fine
    assert (root / "b").read_text() == "x"


def test_the_message_names_the_link_target(tmp_path: Path) -> None:
    (tmp_path / "roadmap.md").symlink_to("payload.md")
    with pytest.raises(SafeWriteError) as e:
        safe_write.check(tmp_path, tmp_path / "roadmap.md")
    assert str(e.value) == f"{tmp_path / 'roadmap.md'} is a symlink (to payload.md), not a regular file"


def _resolve_error(path: Path) -> BaseException:
    try:
        path.resolve()   # pathlib's RuntimeError before Python 3.13, ELOOP after
    except (OSError, RuntimeError) as e:
        return e
    raise AssertionError("no loop")


LOOP_ERRORS = {   # how code that reads, resolves or makes a directory meets a loop -> the error it raises
    "read": lambda p: pytest.raises(OSError, (p / "f").read_text).value,
    "resolve": lambda p: _resolve_error(p / "f"),
    "mkdir": lambda p: pytest.raises(FileExistsError, p.mkdir, exist_ok=True).value,
}


@pytest.mark.parametrize("met_by", list(LOOP_ERRORS))
def test_a_symlink_loop_is_refused_as_the_looping_link(tmp_path: Path, met_by: str) -> None:
    """The CLI boundary (``exit_on_refusal``) gives a loop the rule's refusal, so no command prints a traceback."""
    (tmp_path / "loop").symlink_to("loop")
    refusal = safe_write.loop_refusal(LOOP_ERRORS[met_by](tmp_path / "loop"))
    assert str(refusal) == f"{tmp_path / 'loop'} is a symlink (to loop), not a directory" or (
        met_by == "mkdir" and str(refusal) == f"{tmp_path / 'loop'} is a symlink (to loop), not a regular file or a directory")
    (tmp_path / "file").write_text("x")
    assert safe_write.loop_refusal(pytest.raises(FileExistsError, (tmp_path / "file").mkdir).value) is None


def test_mkdirs_and_write_create_missing_parents_and_keep_a_files_mode(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    assert safe_write.mkdirs(tmp_path, tmp_path / "a" / "b") == tmp_path / "a" / "b"   # an existing real dir is fine
    path = tmp_path / "a" / "b" / "c" / "f"
    safe_write.write(tmp_path, path, b"one")
    path.chmod(0o640)
    safe_write.write(tmp_path, path, "two")
    assert path.read_text() == "two" and path.stat().st_mode & 0o777 == 0o640
    assert sorted(p.name for p in path.parent.iterdir()) == ["f"]   # no temp file left behind


def test_prune_empty_stops_at_a_link_or_a_non_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "keep" / "a" / "b").mkdir(parents=True)
    (tmp_path / "keep" / "other").write_text("x")
    safe_write.prune_empty(tmp_path, tmp_path / "keep" / "a" / "b")
    assert sorted(p.name for p in (tmp_path / "keep").iterdir()) == ["other"]

    (tmp_path / "target").mkdir()
    (tmp_path / "linked").symlink_to("target")
    safe_write.prune_empty(tmp_path, tmp_path / "linked")
    assert (tmp_path / "linked").is_symlink() and (tmp_path / "target").is_dir()


@pytest.mark.parametrize("dir_fd", [True, False], ids=["descriptors", "no-dir-fd"])
def test_a_link_swapped_in_right_before_replace_is_refused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dir_fd: bool) -> None:
    if not dir_fd:   # as on Windows: M21.37's lstat re-check is the guard
        monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd - {os.open, os.rename, os.replace})
    path, theirs = tmp_path / "root" / "f", tmp_path / "theirs"
    path.parent.mkdir()
    path.write_bytes(OLD)
    theirs.write_bytes(OLD)
    chmod = os.chmod

    def swap(tmp: Path, mode: int) -> None:   # the last step before the re-check: a racer links the destination
        chmod(tmp, mode)
        path.unlink()
        path.symlink_to(theirs)

    monkeypatch.setattr(os, "chmod", swap)
    with pytest.raises(SafeWriteError, match=f"^{path} is a symlink"):
        safe_write.write(path.parent, path, "new\n", mode=0o644)
    monkeypatch.undo()
    assert theirs.read_bytes() == OLD and path.is_symlink()
    assert sorted(p.name for p in path.parent.iterdir()) == ["f"]   # the temp file is gone


def swap_at_open(monkeypatch: pytest.MonkeyPatch, opened: Path, swapped: Path, to: Path, before: bool = False) -> None:
    """A racer: once ``opened`` is opened as a directory (right before ``opened`` is opened by its path, with
    ``before``), ``swapped`` is moved to ``<name>.real`` and a symlink to ``to`` takes its place (once)."""
    real_open, aside = os.open, swapped.with_name(swapped.name + ".real")

    def swap() -> None:
        if not os.path.lexists(aside):
            swapped.rename(aside)
            swapped.symlink_to(to)

    def racing_open(path, flags, *args, **kwargs):
        if before and flags & os.O_DIRECTORY and path == opened:
            swap()
        fd = real_open(path, flags, *args, **kwargs)
        if not before and flags & os.O_DIRECTORY and os.path.isdir(opened) \
                and os.path.samestat(os.fstat(fd), os.lstat(opened)):
            swap()
        return fd

    monkeypatch.setattr(os, "open", racing_open)
    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {racing_open})


def _generated(tmp_path: Path):
    root = tmp_path / "p"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    assert run_init_project(root, profiles="none") == 0
    return root / "roadmap.md", lambda: regenerate_generated_files(root)


def _managed(tmp_path: Path):
    path = tmp_path / "p" / ".gitignore"
    path.parent.mkdir()
    path.write_bytes(OLD)
    return path, lambda: apply_managed_block(path, ["x"], strict=True)


def _nested(tmp_path: Path):
    path = tmp_path / "p" / "sub" / "f"
    path.parent.mkdir(parents=True)
    path.write_bytes(OLD)
    return path, lambda: safe_write.write(tmp_path / "p", path, "new\n")


# writer -> setup returning (destination, run); the generated file and the managed block sit in the root itself
RACED_WRITERS = {"generated file": _generated, "managed block": _managed, "nested file": _nested}


@pytest.mark.skipif(not hasattr(os, "O_DIRECTORY"), reason="no directory descriptors here")
@pytest.mark.parametrize("swapped", ["destination", "parent"])
@pytest.mark.parametrize("writer", list(RACED_WRITERS))
def test_a_link_swapped_in_after_the_walk_is_refused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writer: str, swapped: str) -> None:
    path, run = RACED_WRITERS[writer](tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / path.name).write_bytes(OLD)
    target = path if swapped == "destination" else path.parent
    swap_at_open(monkeypatch, path.parent, target, outside / path.name if swapped == "destination" else outside)
    try:
        result = run()
    except SafeWriteError as e:
        result = f"refused: {e}"
    monkeypatch.undo()

    assert str(result).startswith(f"refused: {target} is a symlink (to {outside}")
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == {path.name: OLD}
    real = path.parent if swapped == "destination" else path.parent.with_name(path.parent.name + ".real")
    assert not [p.name for p in real.iterdir() if p.name.endswith(".tmp")]   # the temp file is gone


ROOT_OPERATIONS = {
    "write": lambda root, src: safe_write.write(root, root / "made" / "f", "x"),
    "copy": lambda root, src: safe_write.copy(root, src, root / "f"),
    "mkdirs": lambda root, src: safe_write.mkdirs(root, root / "made"),
}


def _swap_after_resolve(monkeypatch: pytest.MonkeyPatch, root: Path, to: Path) -> None:
    """A racer: right after ``root`` is first resolved, it is moved to ``<name>.real`` and linked to ``to``."""
    resolve = Path.resolve

    def racing_resolve(self, *args, **kwargs):
        resolved = resolve(self, *args, **kwargs)
        if self == root and not os.path.lexists(root.with_name(root.name + ".real")):
            root.rename(root.with_name(root.name + ".real"))
            root.symlink_to(to)
        return resolved

    monkeypatch.setattr(Path, "resolve", racing_resolve)


@pytest.mark.skipif(not hasattr(os, "O_DIRECTORY"), reason="no directory descriptors here")
@pytest.mark.parametrize("swapped", ["before-open", "after-resolve"])
@pytest.mark.parametrize("operation", list(ROOT_OPERATIONS))
def test_a_root_swapped_for_a_link_before_it_is_opened_is_refused(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, swapped: str) -> None:
    """The root is resolved once and opened without following a link: a root swapped for a link out right
    after that resolution, or right before it is opened, is refused and nothing lands outside."""
    root, outside, src = tmp_path / "p", tmp_path / "outside", tmp_path / "src"
    root.mkdir()
    outside.mkdir()
    src.write_bytes(b"new\n")
    if swapped == "before-open":
        swap_at_open(monkeypatch, root, root, outside, before=True)
    else:
        _swap_after_resolve(monkeypatch, root, outside)
    with pytest.raises(SafeWriteError, match=f"^{root} is a symlink \\(to {outside}\\), not a directory$"):
        ROOT_OPERATIONS[operation](root, src)
    monkeypatch.undo()
    assert not list(outside.iterdir()) and not list((tmp_path / "p.real").iterdir())


@pytest.mark.skipif(not hasattr(os, "O_DIRECTORY"), reason="no directory descriptors here")
@pytest.mark.parametrize("operation", ["write", "copy"])
def test_a_parent_swapped_after_the_temp_file_leaves_outside_metadata_alone(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str) -> None:
    """A racer swaps the parent for a link out right after the temp file is made, and plants a file with the
    temp file's name there: setting the temp file's mode (``write``) or mode and times (``copy``) leaves it be."""
    parent, outside, src = tmp_path / "p" / "sub", tmp_path / "outside", tmp_path / "src"
    parent.mkdir(parents=True)
    outside.mkdir()
    (parent / "f").write_bytes(OLD)
    src.write_bytes(b"new\n")
    os.chmod(src, 0o600)
    os.utime(src, (1_000_000, 1_000_000))
    real_open, planted = os.open, {}

    def racing_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if flags & os.O_CREAT and flags & os.O_EXCL and not planted:   # the temp file, by name in its parent
            parent.rename(parent.with_name("sub.real"))
            parent.symlink_to(outside)
            theirs = outside / os.fsdecode(path)
            theirs.write_bytes(OLD)
            os.chmod(theirs, 0o666)
            planted[theirs] = os.stat(theirs)
        return fd

    monkeypatch.setattr(os, "open", racing_open)
    monkeypatch.setattr(os, "supports_dir_fd", os.supports_dir_fd | {racing_open})
    with pytest.raises(SafeWriteError, match=f"^{parent} is a symlink"):
        if operation == "write":
            safe_write.write(tmp_path / "p", parent / "f", "new\n", mode=0o600)
        else:
            safe_write.copy(tmp_path / "p", src, parent / "f")
    monkeypatch.undo()
    [(theirs, before)] = planted.items()
    after = os.stat(theirs)
    assert (after.st_mode, after.st_mtime_ns, theirs.read_bytes()) == (before.st_mode, before.st_mtime_ns, OLD)
    assert sorted(p.name for p in outside.iterdir()) == [theirs.name]
    assert sorted(p.name for p in (tmp_path / "p" / "sub.real").iterdir()) == ["f"]   # the temp file is gone
