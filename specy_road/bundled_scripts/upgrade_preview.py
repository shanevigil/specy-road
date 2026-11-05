"""The ``upgrade --dry-run`` preview tree: what it copies, and how it stays apart from the checkout.

The preview applies the refreshes to a temporary copy and validates that, so a
breaking validate error shows before anything is written. Two guarantees:

- **Isolation.** The copy holds only regular files, with every link followed to
  its content, and a fingerprint of the checkout taken before and after
  catches any write that escapes anyway.
- **Parity.** A path the real refresh declines on the checkout (a link it
  refuses, a file not ours, an unreadable file) is put back after the preview
  refresh, so materializing a link never changes whether it is refreshed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from specy_road.bundled_scripts.refresh_stubs import _block_previews, _prefix
from specy_road.git_subprocess import git_text


def preview_files(checkout: Path, project: Path) -> dict[Path, Path]:
    """``{path in the preview tree: the regular file whose bytes it gets}``.

    The inputs are git's tracked and unignored files, every ``.specyrd/`` file,
    and the managed-block files ``refresh-stubs`` previews (``_block_previews``'s
    selection, ignored or not), without ``.git`` or the project's ``work/``. Every
    link is followed to the file or directory it names, so the preview tree
    holds only regular files and no write in it can reach the checkout.
    """
    work = project / "work"
    listed = git_text(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], checkout)
    rels = {Path(r) for r in (listed or "").split("\0") if r}
    if listed is None:
        rels = {p.relative_to(checkout) for p in checkout.rglob("*") if p.is_file() or p.is_symlink()}
    rels |= {p.relative_to(checkout) for d in {checkout, project} for p in (d / ".specyrd").rglob("*")}
    # _block_previews' selection, by name: run against an empty root it creates every managed-block
    # file and reads nothing from the checkout (an unreadable file there stays for the refresh to fail on).
    with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as scratch:
        blocks = _block_previews(Path(empty), _prefix(checkout, project), Path(scratch))
    rels |= {Path(entry.partition(" (")[0]) for entry in blocks}
    files: dict[Path, Path] = {}
    for rel in rels:
        src = checkout / rel
        if ".git" in rel.parts or src.is_relative_to(work):
            continue
        if src.is_file():
            files[rel] = src
        elif src.is_dir():   # a link to a directory: git lists it as one entry
            seen: set[str] = set()
            for dirpath, dirs, names in os.walk(src, followlinks=True):
                seen.add(os.path.realpath(dirpath))
                dirs[:] = [d for d in dirs if os.path.realpath(os.path.join(dirpath, d)) not in seen]
                for name in names:
                    full = Path(dirpath) / name
                    if full.is_file():
                        files[rel / full.relative_to(src)] = full
    return files


def copy_tree(files: dict[Path, Path], dest: Path) -> None:
    """Write ``files`` into ``dest`` as regular files, then commit them once in a fresh git repo."""
    for rel, src in files.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dest / rel)   # follows links: the copy is the content, never the link
        except PermissionError:   # unreadable here: unreadable in the copy too, so every reader fails alike
            (dest / rel).touch()
            (dest / rel).chmod(src.stat().st_mode & 0o777)
    # validate reads git (tracked files for touch zones, ignore rules): one commit of the copy.
    for cmd in (["init", "-q"], ["add", "-A", "--ignore-errors"],
                ["-c", "user.name=specy-road", "-c", "user.email=upgrade@specy-road.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", "upgrade preview"]):
        subprocess.run(["git", "-C", str(dest), *cmd], check=False, capture_output=True)


def fingerprint(checkout: Path, files: dict[Path, Path]) -> dict[str, str]:
    """What the dry run must leave as it was: git's status (ignored files too) and each preview input's hash.

    ``--no-optional-locks`` keeps ``git status`` from rewriting the index, so this writes nothing.
    """
    status = git_text(["--no-optional-locks", "status", "--porcelain=v1", "-z", "--ignored"], checkout) or ""
    out = {f"status {entry}": "" for entry in status.split("\0") if entry}
    for rel, src in files.items():
        try:
            out[rel.as_posix()] = hashlib.sha256(src.read_bytes()).hexdigest()
        except OSError:
            out[rel.as_posix()] = "unreadable"
    return out


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """The paths whose status entry or hash differs between two :func:`fingerprint` results."""
    gone_or_new = {k.removeprefix("status ")[3:] if k.startswith("status ") else k for k in before.keys() ^ after.keys()}
    return sorted(gone_or_new | {k for k in before.keys() & after.keys() if before[k] != after[k]})


def snapshot_declined(copy: Path, declined: set[str]) -> dict[str, bytes | None]:
    """Bytes (``None`` when absent) of each path the real refresh declines, as the copy holds it before refreshing.

    ``declined`` is decided once, on the checkout, by the real refresh's own
    predicates (a link out of the repository or out of the file's directory, a
    file not ours, an unreadable file). A directory, or a file the copy cannot
    read, is left out: no refresh writes either.
    """
    kept: dict[str, bytes | None] = {}
    for rel in declined:
        path = copy / rel
        try:
            if path.is_file():
                kept[rel] = path.read_bytes()
            elif not path.exists():
                kept[rel] = None
        except PermissionError:
            continue
    return kept


def restore_declined(copy: Path, kept: dict[str, bytes | None]) -> None:
    """Undo the preview refresh on exactly the declined paths.

    The copy holds no links, so its refresh writes paths the real one refuses;
    putting those back leaves the copy as a real run leaves the checkout.
    """
    for rel, data in kept.items():
        path = copy / rel
        if data is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        elif path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
