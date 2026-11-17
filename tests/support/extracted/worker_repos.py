"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.support.harness import FAKE
from pathlib import Path
from tests.support.review import make_review_repo, git
import shutil
import sys
from tests.support.harness import worker_roster

def worker_repo(tmp_path: Path) -> Path:
    """A claimed review repo whose roster launches the shared fake harness."""
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    repo = make_review_repo(
        tmp_path,
        orchestration=worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"),
    )
    (repo / ".gitignore").write_text("work/\n")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-qm", "ignore work")
    return repo

def nested_project(tmp_path: Path, roster: str | None = None) -> tuple[Path, Path]:
    """``(git root, project root)`` with the claim's branch checked out under ``sr/``; ``roster`` replaces the fake's."""
    script = tmp_path / "fake.py"
    script.write_text(FAKE)
    flat = make_review_repo(tmp_path, orchestration=roster or worker_roster(f"{sys.executable} {script} {{prompt}} {{session}}"))
    top = tmp_path / "top"
    git(flat, "checkout", "-q", "dev")
    shutil.copytree(flat, top / "sr", ignore=shutil.ignore_patterns(".git"))
    (top / "sr" / ".gitignore").write_text("work/reviews/\nwork/prompt-*.md\nwork/.workers/\nwork/.worktrees/\n")
    (top / ".specyrd").mkdir()
    (top / ".specyrd" / "manifest.json").write_text('{"project_root": "sr"}\n')
    git(top, "init", "-q", "-b", "dev")
    git(top, "config", "user.email", "t@e.com")
    git(top, "config", "user.name", "T")
    git(top, "add", "-A")
    git(top, "commit", "-qm", "graph")
    git(top, "checkout", "-q", "-b", "feature/rm-thing")
    (top / "src").mkdir()
    (top / "src" / "a.py").write_text("print('a')\n")
    git(top, "add", "-A")
    git(top, "commit", "-qm", "impl")
    return top.resolve(), (top / "sr").resolve()
