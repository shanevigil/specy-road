"""M11.68: a re-delegated executor starts from the blocking review findings and the previous worker's last message."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from tests.support.review import review_text, git
from tests.support.profiles import make_profile_repo
from tests.support.cli import run_worker_cli
from tests.support.harness import make_worker_repo, wait_for_worker

from specy_road.orchestration.workers import worker_state as ws
from specy_road.bundled_scripts import role_prompt
from specy_road.review_files import reviews_dir
from tests.support.extracted.rework_findings_in_prompt import (
    executor_prompt,
    file_review,
    stopped_worker,
)








def test_no_blocking_record_and_no_stopped_worker_means_no_rework_section(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    file_review(repo, "sol", git(repo, "rev-parse", "HEAD"), "approve")
    assert "## Rework" not in executor_prompt(repo)


def test_blocking_records_at_the_tip_and_an_earlier_commit_are_inlined(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    tip, earlier = git(repo, "rev-parse", "HEAD"), git(repo, "rev-parse", "HEAD~1")
    file_review(repo, "sol", tip, "block", ["Restore the docstring removed from a.py", "Add a test for the empty case"])
    file_review(repo, "human", earlier, "block", ["Name the new module in the summary"])
    file_review(repo, "opus", tip, "approve")
    text = executor_prompt(repo)
    rework = text[text.index("## Rework"):text.index("\n---\n", text.index("## Rework"))]
    assert "Build on the commits already on `feature/rm-thing`: do not reset, revert, squash or rewrite them" in rework
    assert f"### `sol` blocks `{tip}` (the branch tip)" in rework
    assert "- Restore the docstring removed from a.py\n- Add a test for the empty case" in rework
    assert f"### `human` blocks `{earlier}` (an earlier commit)" in rework
    assert "- Name the new module in the summary" in rework
    assert "`opus` blocks" not in rework and "previous worker" not in rework
    assert text.index("## Rework") < text.index("# Work-packet brief")


def test_a_block_with_no_required_changes_names_its_failing_acceptance(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    d = reviews_dir(repo, "M1.1")
    d.mkdir(parents=True)
    text = review_text(git(repo, "rev-parse", "HEAD"), model="sol", verdict="block", a1="fail")
    (d / "REVIEW-sol.md").write_text(text.replace("required_changes:\n- fix\n", "required_changes: []\n"))
    assert "(no required_changes listed; failing acceptance: A1; read the record's findings)" in executor_prompt(repo)


def test_a_terminated_workers_last_final_message_is_carried(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    stopped_worker(repo, "grok", "terminated", "Implemented A1; A2's test still fails with ```KeyError```.")
    text = executor_prompt(repo)
    assert "### The previous worker's last message (`w-0001`, `grok`, terminated)" in text
    assert "````text\nImplemented A1; A2's test still fails with ```KeyError```.\n````" in text


def test_an_active_latest_worker_carries_nothing(tmp_path: Path) -> None:
    repo = make_profile_repo(tmp_path)
    stopped_worker(repo, "grok", "failed", "old attempt")
    stopped_worker(repo, "opus", "idle", "current attempt")
    assert "## Rework" not in executor_prompt(repo)


def test_delegate_rework_takeover_by_a_different_model(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    tip = git(repo, "rev-parse", "HEAD")
    file_review(repo, "sol", tip, "block", ["Cover the empty roster"])
    stopped_worker(repo, "grok", "failed", "Model unavailable after commit 2; A2 is left.")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--rework", "--json",
                          "--repo-root", str(repo)) == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert out["created"] and out["worker_id"] == "w-0002" and out["model"] == "opus"
    assert "1 blocking review(s) (sol) and w-0001's last message (grok, failed)" in captured.err
    prompt = (repo / "work" / "prompt-M1.1-executor-opus.md").read_text(encoding="utf-8")
    assert "- Cover the empty roster" in prompt
    assert "### The previous worker's last message (`w-0001`, `grok`, failed)" in prompt
    assert "Model unavailable after commit 2; A2 is left." in prompt
    wait_for_worker(repo, "w-0002")


def test_delegate_rework_refusals(tmp_path: Path, capsys) -> None:
    repo, _ = make_worker_repo(tmp_path)
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--rework", "--repo-root", str(repo)) == 1
    assert "nothing to rework on M1.1" in capsys.readouterr().err
    stopped_worker(repo, "grok", "idle", "still mine")
    assert run_worker_cli("worker", "delegate", "M1.1", "--model", "opus", "--rework", "--repo-root", str(repo)) == 1
    assert "w-0001 is still active on M1.1 (idle)" in capsys.readouterr().err
    assert not (repo / "work" / "prompt-M1.1-executor-opus.md").exists()
