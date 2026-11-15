"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.same.git_84c8ad8f55f9 import git
from specy_road.review_files import reviews_dir

def ready(repo: Path, agent: str) -> None:
    """Shared test helper."""
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"READY-{agent}.md").write_text(
        f"---\nnode_id: M1.1\nagent: {agent}\nbranch: feature/rm-thing\ncommit: {git(repo, 'rev-parse', 'HEAD')}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n---\n"
    )
