"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.same.run_651387813ee4 import run
from tests.support.same.git_84c8ad8f55f9 import git
import json
from specy_road.review_files import reviews_dir

ONE_AI = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
"""

def ready(repo: Path, commit: str | None = None) -> None:
    """Shared test helper."""
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    commit = commit or git(repo, "rev-parse", "HEAD")
    (d / "READY-composer.md").write_text(
        f"---\nnode_id: M1.1\nagent: composer\nbranch: feature/rm-thing\ncommit: {commit}\n"
        f"base: {git(repo, 'rev-parse', 'dev')}\nchanged_paths: [src/a.py]\n---\n"
    )

def status(repo: Path, capsys) -> dict:
    """One node's status; its exit is 0 when the gate is met and 1 when it is not."""
    capsys.readouterr()
    code = run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    st = json.loads(capsys.readouterr().out)["nodes"][0]
    assert code == (0 if st["policy_met"] else 1), st["state"]
    return st
