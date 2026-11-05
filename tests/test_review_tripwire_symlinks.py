"""M8.3 A2: the tripwire decides on paths as text and follows no symlink (Sol-low's block at d36faf66).

The hand-off exclusion resolved each ``git status`` entry, so a tracked file replaced by a symlink into the
hand-off directory (``T src/a.py``) was excluded as if it were the reviewer's notes. Now an entry is excluded only
when the path git prints lies under the hand-off directory, whose place the snapshot before the run fixes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.review_delegate_helpers import delegate_repo, set_steps, verdict_step, wrote_paths
from tests.review_repo_helpers import git, make_review_repo
from tests.test_models_and_prompt import run_main
from tests.test_review_record_write import GENERIC

from specy_road import review_files as rf
from specy_road.bundled_scripts import role_prompt
from specy_road.review_delegate import delegate
from specy_road.review_record_write import snapshot, written


def _targets(repo: Path, tmp_path: Path) -> dict[str, str]:
    notes = rf.reviews_dir(repo, "M1.1") / "notes-opus.md"
    outside = tmp_path / "outside.txt"
    outside.write_text("outside the repository\n")
    return {"notes-absolute": str(notes), "notes-relative": os.path.relpath(notes, repo / "src"),
            "outside-repo": str(outside)}


@pytest.mark.parametrize("target", ["notes-absolute", "notes-relative", "outside-repo"])
@pytest.mark.parametrize("rel", ["src/a.py", "new-link"])          # a tracked file's typechange, a new symlink
def test_a_symlink_written_outside_the_hand_off_directory_is_a_review_failure(tmp_path: Path, rel: str,
                                                                               target: str) -> None:
    repo, spec = delegate_repo(tmp_path)
    to = _targets(repo, tmp_path)[target]
    set_steps(repo, spec, {**verdict_step(repo), "symlink": {"path": str(repo / rel), "target": to}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert (repo / rel).is_symlink()
    if rel == "src/a.py":
        assert git(repo, "status", "--porcelain", "src/a.py") == "T src/a.py"   # git reports a typechange
    assert run["state"] == "incomplete" and run["outcome"] == "review_failure"
    assert wrote_paths(run["reason"]) == [rel]
    assert not rf.review_path(repo, "M1.1", "opus").exists()


def test_prompt_channel_cli_reports_a_typechange_into_the_hand_off_directory(tmp_path: Path, capsys) -> None:
    repo, spec = delegate_repo(tmp_path, GENERIC)
    notes = rf.reviews_dir(repo, "M1.1") / "notes-gem.md"
    set_steps(repo, spec, {**verdict_step(repo, model="gem"), "plain": True,
                           "symlink": {"path": str(repo / "src" / "a.py"), "target": str(notes)}})
    assert run_main(role_prompt, "M1.1", "--model", "gem", "--role", "reviewer", "--channel", "cli",
                    "--repo-root", str(repo)) == 1
    failure = next(line for line in capsys.readouterr().err.splitlines() if line.startswith("review_failure: "))
    assert wrote_paths(failure) == ["src/a.py"] and not rf.review_path(repo, "M1.1", "gem").exists()


def test_a_symlink_into_the_checkout_inside_the_hand_off_directory_is_one_entry_never_followed(tmp_path: Path) -> None:
    repo, spec = delegate_repo(tmp_path)
    link = rf.reviews_dir(repo, "M1.1") / "src-link"
    set_steps(repo, spec, {**verdict_step(repo), "symlink": {"path": str(link), "target": str(repo / "src")}})
    run = delegate(repo, "M1.1", "opus", sleep=lambda s: None)
    assert run["outcome"] == "review_failure" and wrote_paths(run["reason"]) == ["work/reviews/M1.1/src-link"]


def test_the_hand_off_directory_replaced_by_a_symlink_is_reported_and_its_place_is_not_re_resolved(
        tmp_path: Path) -> None:
    """The snapshot after the run reuses the place the first fixed: a reviewer that points ``work/reviews/M1.1``
    at ``src/`` neither moves the exclusion onto ``src/`` nor hides ``src/`` writes."""
    repo = make_review_repo(tmp_path)
    reviews = rf.reviews_dir(repo, "M1.1")
    reviews.mkdir(parents=True, exist_ok=True)
    (reviews / "PACKET.md").write_text("packet\n")
    before = snapshot(repo, reviews, "opus")
    reviews.rename(tmp_path / "moved-away")
    reviews.symlink_to(repo / "src", target_is_directory=True)
    (repo / "src" / "a.py").write_text("changed through the link\n")
    wrote = written(before, snapshot(repo, reviews, "opus", before))
    assert "src/a.py" in wrote and "work/reviews/M1.1" in wrote and "work/reviews/M1.1/PACKET.md" in wrote
    assert json.dumps(wrote)                                                    # plain strings, as reported
