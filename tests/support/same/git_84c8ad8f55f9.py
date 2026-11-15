"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
import subprocess

def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return r.stdout.strip()
