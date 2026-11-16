"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import subprocess

def git(repo: Path, *args: str) -> None:
    """Shared test helper."""
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
