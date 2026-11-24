"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.same.git_84c8ad8f55f9 import git

FILES = ("pkg/worker_ops_launch.py", "pkg/worker_ops_stop.py", "pkg/core.py", "docs/a.md")

UNTRACKED = "touch zones that match no tracked file and are not a directory"

def zone_git_repo(root: Path, files=FILES) -> Path:
    for rel in files:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("x = 1\n", encoding="utf-8")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root
