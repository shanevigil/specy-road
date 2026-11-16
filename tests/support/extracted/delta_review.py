"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from typing import Callable
from tests.support.review import NODE, git
from pathlib import Path
from tests.support.review import advance_dev
from specy_road.review_files import archive_review
from tests.support.review import commit_file
from tests.support.review import make_review_repo
import pytest
from specy_road.bundled_scripts import review_cli
from tests.support.review import review_text
from specy_road.review_files import reviews_dir

ROSTER = """version: 1
roster:
  - {id: opus, family: anthropic, roles: [reviewer]}
  - {id: sonnet, family: anthropic, roles: [reviewer]}
  - {id: sol, family: openai, roles: [reviewer]}
policy: {reviewers_required: 2, reviewers_distinct_families: true%s}
"""

TEST_FILE = "src/tests/test_a.py"

TEST_SRC = "def test_a():\n    assert 1\n"

def file(repo: Path, model: str, commit: str, verdict: str = "approve", delta_from: str | None = None,
          drop: str | None = None, findings: dict | None = None) -> None:
    """File a record as `review record` does: the live REVIEW-<model>.md plus a copy under history/.
    ``drop`` leaves out that acceptance id's result, so the record is incomplete for the brief."""
    found = {"correctness": [], "regression": [], "boundary": [], "test_integrity": [], **(findings or {})}
    text = review_text(commit, model=model, verdict=verdict, a1="pass" if verdict == "approve" else "fail",
                       findings=found)
    text = text.replace("notes\n", f"{model} notes on {commit[:7]}\n")
    if drop:
        text = text.replace(f"  {drop}: pass\n", "")
    if delta_from:
        text = text.replace("---\n", f"---\ndelta_from: '{delta_from}'\n", 1)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True, exist_ok=True)
    (d / f"REVIEW-{model}.md").write_text(text)
    archive_review(repo, "M1.1", model, text)

FINDING = "src/b.py divides by zero"

SHEET = "# M1.1 Thing\n\n## Intent\n\nDo the thing.\n\n## Tier\n\n%s: a small change.\n"

def ready(repo: Path, fix_of: str | None) -> int:
    """composer's READY at HEAD via `specy-road ready`, naming ``fix_of`` when given."""
    with pytest.raises(SystemExit) as e:
        review_cli.main(["ready", "M1.1", "--model", "composer", "--verify", "true=0",
                         *(["--fix-of", fix_of] if fix_of else []), "--repo-root", str(repo)])
    return e.value.code

def fix_round(tmp_path: Path, *, fix: Callable[[Path], object] | None = None, fix_of: str | None = "sol",
              tier: str | None = "plain", branch_tier: str | None = None, policy: str = "",
              roster: str = ROSTER, delta: bool = False) -> tuple[Path, str, str]:
    """``(repo, P, F)``: opus (anthropic) approves ``P``, sol (openai) blocks it with :data:`FINDING`, and ``fix``
    (default: commit ``src/b.py``) makes the fix commit ``F``; composer's READY at ``F`` names ``<fix_of>@P``.
    The integration branch's sheet names ``tier`` (``None``: today's sheet, which has no ``## Tier``);
    ``branch_tier`` sets the branch's own copy before ``P``. ``delta``: opus approved ``P``'s parent in full and
    ``P`` (a test-only change) as a delta review from it."""
    repo = make_review_repo(tmp_path, orchestration=roster % policy)
    if branch_tier:
        commit_file(repo, NODE["planning_dir"], SHEET % branch_tier, "branch sheet")
    basis = git(repo, "rev-parse", "HEAD")
    if delta:
        file(repo, "opus", basis)
    approved = commit_file(repo, TEST_FILE, TEST_SRC, "first round")
    file(repo, "opus", approved, delta_from=basis if delta else None)
    file(repo, "sol", approved, verdict="block", findings={"correctness": [FINDING]})
    if tier:
        advance_dev(repo, NODE["planning_dir"], SHEET % tier)
    (fix or (lambda r: commit_file(r, "src/b.py", "x = 1\n", "fix")))(repo)
    assert ready(repo, fix_of and f"{fix_of}@{approved}") == 0
    return repo, approved, git(repo, "rev-parse", "HEAD")
