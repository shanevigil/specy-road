"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.support.same.run_651387813ee4 import run
from tests.support.review import commit_file, git
import json
from tests.support.review import review_text

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
"""

def block_round(repo: Path, n: int, a1: str = "fail") -> None:
    """One more commit, blocked by opus."""
    commit_file(repo, f"src/r{n}.py", f"r = {n}\n", f"fix {n}")
    notes = repo.parent / "notes.md"
    text = review_text(git(repo, "rev-parse", "HEAD"), model="opus", verdict="block", a1=a1)
    front, _body = text.rsplit("---\n", 1)
    notes.write_text(front + "---\n" + f"round {n}: the heading case still warns\n")
    assert run("review", "record", "M1.1", "--model", "opus", "--verdict", "block",
                "--file", str(notes), "--repo-root", str(repo)) == 0

def status(repo: Path, capsys) -> tuple[int, dict]:
    """Shared test helper."""
    capsys.readouterr()
    code = run("handoff", "status", "M1.1", "--json", "--repo-root", str(repo))
    return code, json.loads(capsys.readouterr().out)["nodes"][0]
