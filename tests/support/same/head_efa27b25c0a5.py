"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.same.git_84c8ad8f55f9 import git

def head(repo: Path) -> str:
    """Shared test helper."""
    return git(repo, "rev-parse", "HEAD")
