"""``human:`` acceptance items: reviewers skip them, ``finish-this-task`` waits for a recorded decision (M11.9).

An item a person must satisfy (approve wording, supply a link) made both
reviewers spend full runs and then block. Marked ``human:`` it is ``n/a`` for a
review, and the leaf finishes only once the planning sheet records the decision.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road.bundled_scripts import finish_task
from specy_road.bundled_scripts.role_prompt_rca import reviewer_preamble
from specy_road.finish_task_gates import human_acceptance_ids, recorded_decisions, undecided_human_items
from tests.review_repo_helpers import NODE, commit_file, git, make_review_repo

HUMAN_NODE = {**NODE, "acceptance": ["a.py exists", "human: the maintainer approves the wording"]}
SHEET = NODE["planning_dir"]


def _human_repo(tmp_path: Path) -> Path:
    repo = make_review_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    chunk.write_text(json.dumps({"nodes": [HUMAN_NODE]}), encoding="utf-8")
    git(repo, "commit", "-qam", "mark A2 human")
    return repo


def test_marker_and_decision_lines() -> None:
    assert human_acceptance_ids(HUMAN_NODE) == ["A2"]
    assert human_acceptance_ids(NODE) == []
    sheet = "## Decisions and notes\n\n- [x] A2: wording approved by the maintainer\n- [ ] A3\nA1: no\n"
    assert recorded_decisions(sheet) == {"A2": "wording approved by the maintainer", "A1": "no"}


def test_reviewer_is_told_to_skip_a_human_item() -> None:
    text = "\n".join(reviewer_preamble("M1.1", "r1"))
    assert "`human:`" in text and "mark it `n/a`" in text and "write `human` as its reason" in text


def test_finish_refuses_until_the_sheet_records_the_decision(tmp_path: Path, capsys) -> None:
    repo = _human_repo(tmp_path)
    before = git(repo, "rev-parse", "HEAD")
    assert undecided_human_items(repo, HUMAN_NODE) == ["A2"]

    with pytest.raises(SystemExit) as e:
        finish_task.main(["--repo-root", str(repo)])

    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "error: M1.1 has human acceptance item(s) with no recorded decision: A2." in err
    assert f"`- A2: <decision, who and when>` in {SHEET}" in err
    assert "implementation review is required" not in err
    assert git(repo, "rev-parse", "HEAD") == before

    commit_file(repo, SHEET, "# M1.1 Thing\n\n## Intent\n\nDo the thing.\n\n## Decisions and notes\n\n"
                "- [x] A2: wording approved by the maintainer 2026-11-02\n\n## References\n", "record decision")
    assert undecided_human_items(repo, HUMAN_NODE) == []

    with pytest.raises(SystemExit):
        finish_task.main(["--repo-root", str(repo)])

    err = capsys.readouterr().err
    assert "no recorded decision" not in err
    assert "implementation review is required" in err   # the next gate, as before
