"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.support.pickup import FEATURE
from pathlib import Path
import subprocess

def git(root: Path, *args: str) -> str:
    """Shared test helper."""
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()

def claimed_on(root: Path, ref: str) -> bool:
    """Shared test helper."""
    return "leaf-one" in git(root, "show", f"{ref}:roadmap/registry.yaml")

def branches(root: Path) -> list[str]:
    """Shared test helper."""
    return git(root, "branch", "--format=%(refname:short)").split()

def assert_nothing_claimed(root: Path, main_before: str) -> None:
    """Shared test helper."""
    assert git(root, "rev-parse", "main") == main_before
    assert git(root, "rev-parse", "origin/main") == main_before
    assert not claimed_on(root, "main")
    assert FEATURE not in branches(root)
