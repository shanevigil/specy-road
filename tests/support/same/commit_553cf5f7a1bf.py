"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.same.git_df16ee62bf81 import git

def commit(repo: Path, message: str) -> None:
    """Shared test helper."""
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
