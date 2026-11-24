"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import os
import pytest

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
