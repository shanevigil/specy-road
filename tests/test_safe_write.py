"""M21.37: the one safe-write rule, per operation (specy_road/safe_write.py)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from specy_road import safe_write
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


def test_a_link_swapped_in_right_before_replace_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
