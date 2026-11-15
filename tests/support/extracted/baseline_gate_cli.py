"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.support.pickup import FEATURE
from pathlib import Path
import subprocess

def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()

def _claimed_on(root: Path, ref: str) -> bool:
    return "leaf-one" in _git(root, "show", f"{ref}:roadmap/registry.yaml")

def _branches(root: Path) -> list[str]:
    return _git(root, "branch", "--format=%(refname:short)").split()

def _assert_nothing_claimed(root: Path, main_before: str) -> None:
    assert _git(root, "rev-parse", "main") == main_before
    assert _git(root, "rev-parse", "origin/main") == main_before
    assert not _claimed_on(root, "main")
    assert FEATURE not in _branches(root)
