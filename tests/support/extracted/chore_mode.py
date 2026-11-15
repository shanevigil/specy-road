"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from specy_road.agent_ignores import apply_agent_ignores
from specy_road.bundled_scripts import chore_cli
from tests.support.review import commit_file, git
from tests.support.review import make_review_repo
import pytest

def run_chore_cli(*args: str) -> int:
    with pytest.raises(SystemExit) as e:
        chore_cli.main(list(args))
    return e.value.code or 0

_RULES = ("# Rules\n\nRead the docs.\n<!-- prevents: drift | enforced: advisory | ref: x -->\n"
          "Run validate.\n<!-- prevents: bad graphs | enforced: specy-road validate | ref: y -->\n")

def garden_repo(tmp_path: Path, *, tag: bool = True, cadence: int | None = None) -> Path:
    """A repo on ``dev`` with one finding of each class in its last commit; ``.gitignore`` is the managed lines only."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    (repo / ".gitignore").unlink()
    apply_agent_ignores(repo)                                             # as init project writes it
    git(repo, "add", ".gitignore", ".cursorindexingignore")
    git(repo, "commit", "-qm", "managed ignores")
    policy = "version: 1\npolicy:\n  ratchet_paths:\n    - constraints/base.txt\n" + (
        f"  garden_cadence_days: {cadence}\n" if cadence else "")
    for rel, text in (("roadmap/orchestration.yaml", policy), ("constraints/base.txt", "a\n")):
        commit_file(repo, rel, text, f"add {rel}")
    if tag:
        git(repo, "tag", "v1")
    for rel, text in (("constraints/base.txt", "a\nb\nc\n"),
                      ("docs/guide.md", "# Guide\n\nRun `specy-road grind` then run `specy-road validate`.\n"),
                      ("AGENTS.md", "# Agents\n\n- specy-road nope --flag\n"), (".specyrd/AGENTS.md", _RULES)):
        commit_file(repo, rel, text, f"drift in {rel}")
    return repo

def _roadmap_bytes(repo: Path) -> dict[str, bytes]:
    return {p.relative_to(repo).as_posix(): p.read_bytes()
            for base in ("roadmap", "planning") if (repo / base).is_dir()
            for p in sorted((repo / base).rglob("*")) if p.is_file()}
