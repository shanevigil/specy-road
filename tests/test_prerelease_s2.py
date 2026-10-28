"""Pre-release §2 findings: reviewer precondition, merge-landing retry, work/ file cleanup."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tests.review_repo_helpers import make_review_repo

from specy_road.bundled_scripts.role_prompt import build_prompt
from specy_road.review_files import PACKET_NAME, reviews_dir

ROSTER = """version: 1
roster:
  - {id: human, family: human, roles: [coordinator, reviewer]}
  - {id: rev, family: openai, roles: [reviewer]}
policy: {reviewers_required: 1}
"""


def test_reviewer_precondition_ignores_bookkeeping_but_not_source_changes(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path, orchestration=ROSTER)
    (repo / "work").mkdir()
    (repo / "work" / "brief-M1.1.md").write_text("# brief\n")                 # do-next-available-task
    (repo / "work" / "implementation-summary-M1.1.md").write_text("Did it.\n")  # the executor
    reviews_dir(repo, "M1.1").mkdir(parents=True)
    (reviews_dir(repo, "M1.1") / PACKET_NAME).write_text("# packet\n")
    text, _prof, err = build_prompt(repo, "M1.1", role="reviewer", model="rev")
    assert err is None
    check = re.search(r"or `(git status [^`]+)` lists changes you did not make", text).group(1)

    def dirty() -> str:
        return subprocess.run(check, shell=True, cwd=repo, capture_output=True, text=True, check=True).stdout

    assert dirty() == ""
    (repo / "src" / "b.py").write_text("x = 1\n")
    assert dirty() == "?? src/b.py\n"
