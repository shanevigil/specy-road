"""``finish-this-task`` refuses a leaf whose planning sheet is still the scaffold (M3.14).

Acceptance criteria are enough for pickup to hand the leaf over, but a node
closed with the toolkit's placeholder text as its sheet leaves no record of
what it set out to do. ``--allow-scaffold-planning`` is the explicit opt-out.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts import finish_task
from specy_road.bundled_scripts.brainstorm_promote import seed_planning_sheet
from specy_road.bundled_scripts.brainstorm_session import Idea
from specy_road.bundled_scripts.planning_sheet_bootstrap import render_feature_sheet_template
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo

SHEET = NODE["planning_dir"]


def _scaffold(repo: Path) -> str:
    commit_file(repo, SHEET, render_feature_sheet_template(NODE["id"]), "scaffold sheet")
    return "scaffold-planning's placeholder under ## Intent"


def _promote(repo: Path) -> str:
    _scaffold(repo)
    seed_planning_sheet(repo, dict(NODE), Idea(id="i-1", title="Thing", rationale="Needed."))
    git(repo, "commit", "-qam", "promote")
    return "brainstorm promote's placeholder under ## Intent"


@pytest.mark.parametrize("unwrite", [_scaffold, _promote])
@pytest.mark.parametrize("allow", [False, True])
def test_finish_refuses_an_unwritten_sheet_unless_allowed(tmp_path: Path, capsys, unwrite, allow: bool) -> None:
    repo = make_review_repo(tmp_path)
    placeholder = unwrite(repo)
    before = git(repo, "rev-parse", "HEAD")
    argv = ["--repo-root", str(repo), *(["--allow-scaffold-planning"] if allow else [])]

    with pytest.raises(SystemExit) as e:
        finish_task.main(argv)

    assert e.value.code == 1
    err = capsys.readouterr().err
    refused = f"error: the planning sheet for M1.1 was never written: {SHEET} still has {placeholder}"
    assert (refused in err) is not allow
    assert ("--allow-scaffold-planning" in err) is not allow
    # The opt-out only gets past this gate; the review gate after it still applies.
    assert ("implementation review is required" in err) is allow
    assert git(repo, "rev-parse", "HEAD") == before


def test_a_written_sheet_is_not_refused(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)

    with pytest.raises(SystemExit):
        finish_task.main(["--repo-root", str(repo)])

    err = capsys.readouterr().err
    assert "was never written" not in err
    assert "implementation review is required" in err
