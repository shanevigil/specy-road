"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.same.git_84c8ad8f55f9 import git
import subprocess
from specy_road.git_workflow_config import validate_git_workflow_dict

COVERED, UNCOVERED = "src/engine", "lib"

def add_nested_repo(project: Path, rel: str, branch: str) -> Path:
    """A repository at ``project/rel`` on ``branch``, pushed to its own bare origin, ignored and configured in ``project``.

    The main repository must be on its integration branch; the config commit lands there. A second call
    adds a second repository to the same list.
    """
    nested = project / rel
    nested.mkdir(parents=True)
    git(nested, "init", "-q", "-b", branch)
    git(nested, "config", "user.email", "t@e.com")
    git(nested, "config", "user.name", "T")
    (nested / "core.py").write_text("x = 1\n", encoding="utf-8")
    git(nested, "add", "-A")
    git(nested, "commit", "-qm", "nested root")
    origin = project.parent / (rel.replace("/", "+") + "-origin.git")
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    git(nested, "remote", "add", "origin", str(origin))
    git(nested, "push", "-q", "-u", "origin", branch)
    ignore = project / ".gitignore"
    ignore.write_text((ignore.read_text() if ignore.is_file() else "") + f"{rel}/\n", encoding="utf-8")
    cfg = project / "roadmap" / "git-workflow.yaml"
    text = cfg.read_text()
    cfg.write_text(text + ("" if "nested_repos:" in text else "nested_repos:\n") + f"  - {rel}\n", encoding="utf-8")
    git(project, "add", ".gitignore", "roadmap/git-workflow.yaml")
    git(project, "commit", "-qm", "nested repo")
    return nested

def cfg(extra: dict) -> str | None:
    """Shared test helper."""
    return validate_git_workflow_dict({"version": 1, "integration_branch": "main", "remote": "origin", **extra})
