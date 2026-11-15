"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import subprocess

def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
