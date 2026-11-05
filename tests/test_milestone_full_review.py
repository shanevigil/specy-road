"""A milestone gets one full review of its combined change before it is marked complete (M11.13).

``policy.milestone_full_review`` (default on) holds the ancestor rollup when the
last leaf under a milestone finishes; ``review-packet <MILESTONE_ID>`` diffs from
the first leaf's branch point to the integration tip; approval through
``mark-implementation-reviewed <MILESTONE_ID>`` sets the milestone Complete.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.milestone_repo_helpers import (
    LEAVES, branch_leaf, chunk_path, land_leaf, make_milestone_repo, merge_leaf, set_status,
)
from tests.review_repo_helpers import commit_file, git

from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.finish_ancestor_rollup import complete_rolled_up_ancestors
from specy_road.review_files import reviews_dir
from specy_road.review_target import resolve_target

POLICY_OFF = "version: 1\npolicy: {milestone_full_review: false}\n"


def _statuses(root: Path) -> dict[str, str]:
    return {n["id"]: n["status"] for n in load_json_chunk(chunk_path(root))}


def _effective_rollup(root: Path, nid: str) -> str:
    return next(n["rollup_status"] for n in load_roadmap(root)["nodes"] if n["id"] == nid)


def set_node_status(root: Path, nid: str, status: str) -> None:
    """Public status helper for other test modules (M13.4); same as ``milestone_repo_helpers.set_status``."""
    set_status(root, nid, status)


def _review(root: Path, model: str = "human", commit: str | None = None) -> None:
    d = reviews_dir(root, "M2")
    d.mkdir(parents=True, exist_ok=True)
    data = {"node_id": "M2", "model": model, "date": "2026-11-02", "verdict": "approve",
            "commit": commit or git(root, "rev-parse", "dev"), "acceptance": {},
            "findings": {"correctness": [], "regression": [], "boundary": [], "test_integrity": []},
            "commands_rerun": [], "required_changes": [], "fresh_session": True, "authored_fix": False,
            "is_coordinator": False}
    (d / f"REVIEW-{model}.md").write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---\nnotes\n")


def _cli(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as e:
        review_cli.main(argv)
    return e.value.code or 0


def _mir(root: Path, *args: str) -> int:
    with pytest.raises(SystemExit) as e:
        mir.main([*args, "--repo-root", str(root)])
        raise SystemExit(0)
    return e.value.code or 0


def test_milestone_target_is_the_integration_tip_from_the_first_leaf_branch_point(tmp_path: Path) -> None:
    root = make_milestone_repo(tmp_path)
    graph = git(root, "rev-list", "--max-parents=0", "dev")   # alpha branched here
    t = resolve_target(root, "M2")
    assert t.milestone and t.ref == "refs/heads/dev"
    assert t.commit == git(root, "rev-parse", "dev")
    assert t.base == graph   # alpha branched from the graph commit; beta's later branch point does not move it
    assert git(root, "diff", "--name-only", f"{t.base}...{t.commit}").split() == [
        "roadmap/phases/M2.json", "roadmap/registry.yaml", "src/alpha.py", "src/beta.py"]


def test_milestone_packet_covers_both_leaves_and_base_overrides(tmp_path: Path) -> None:
    root = make_milestone_repo(tmp_path)
    tip = git(root, "rev-parse", "dev")
    text = rp.build_packet(root, "M2", ref=None, verify_cmds=[])
    assert f"- **Commit under review:** `{tip}` (`refs/heads/dev`)" in text
    assert "(first parent of the oldest leaf registration)" in text
    assert "**Milestone full review:** the combined change of its leaves (`M2.1`, `M2.2`)" in text
    assert "mark-implementation-reviewed M2" in text
    assert rp.MILESTONE_SUMMARY in text
    assert "+print('alpha')" in text and "+print('beta')" in text
    later = rp.build_packet(root, "M2", ref=None, verify_cmds=[], base="dev~1")   # only beta's merge
    assert "+print('beta')" in later and "+print('alpha')" not in later


def test_milestone_packet_without_a_registration_commit_needs_base(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path, land=False)
    for nid in LEAVES:   # finished straight on dev, with no pickup commit to anchor the range
        set_status(root, nid, "Complete")
    git(root, "add", "roadmap/phases/M2.json")
    git(root, "commit", "-qm", "landed without pickup")
    with pytest.raises(SystemExit):
        rp.build_packet(root, "M2", ref=None, verify_cmds=[])
    assert "pass --base" in capsys.readouterr().err


def test_rollup_is_held_until_the_milestone_full_review_passes(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path)
    assert complete_rolled_up_ancestors(root, "M2.2") == []
    assert _statuses(root)["M2"] == "Not Started"
    out = capsys.readouterr().out
    assert "[hold] M2 rolled up to Complete but its full review is not approved at refs/heads/dev" in out
    assert "specy-road review-packet M2" in out and "specy-road mark-implementation-reviewed M2" in out
    assert reviews_dir(root, "M2").is_dir()   # so handoff status lists the milestone
    _review(root)
    assert complete_rolled_up_ancestors(root, "M2.2") == ["roadmap/phases/M2.json"]
    assert _statuses(root)["M2"] == "Complete"


def test_policy_off_restores_the_plain_rollup(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path, orchestration=POLICY_OFF)
    assert complete_rolled_up_ancestors(root, "M2.2") == ["roadmap/phases/M2.json"]
    assert _statuses(root)["M2"] == "Complete"
    assert "[hold]" not in capsys.readouterr().out


def test_effective_rollup_is_held_until_approval_and_complete_when_policy_is_off(tmp_path: Path) -> None:
    """Sol R1: consumers of load_roadmap must not see Complete while the full review is pending."""
    root = make_milestone_repo(tmp_path)
    complete_rolled_up_ancestors(root, "M2.2")
    assert _statuses(root)["M2"] == "Not Started"
    assert _effective_rollup(root, "M2") == "In Progress"
    _review(root)
    complete_rolled_up_ancestors(root, "M2.2")
    assert _statuses(root)["M2"] == "Complete"
    assert _effective_rollup(root, "M2") == "Complete"
    off = make_milestone_repo(tmp_path / "off", orchestration=POLICY_OFF)
    complete_rolled_up_ancestors(off, "M2.2")
    assert _effective_rollup(off, "M2") == "Complete"


def test_load_roadmap_holds_rollup_when_repo_root_is_not_resolved() -> None:
    """Grok R1: demote_pending_milestone_rollups must not crash when repo_root and chunk paths disagree on /var vs /private/var."""
    from tempfile import TemporaryDirectory

    from specy_road.bundled_scripts.roadmap_load import load_roadmap

    with TemporaryDirectory() as d:
        root = make_milestone_repo(Path(d))
        complete_rolled_up_ancestors(root, "M2.2")
        node = next(n for n in load_roadmap(root)["nodes"] if n["id"] == "M2")
        assert node["rollup_status"] == "In Progress"
        assert node["status"] == "Not Started"


def test_handoff_status_and_review_list_show_a_milestone_awaiting_its_full_review(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path)
    reviews_dir(root, "M2").mkdir(parents=True)
    assert _cli(["handoff", "status", "M2", "--repo-root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "M2: awaiting_full_review — refs/heads/dev @" in out
    assert "milestone full review pending (policy.milestone_full_review): specy-road review-packet M2" in out
    assert _cli(["review", "list", "M2", "--repo-root", str(root)]) == 0
    assert "specy-road review-packet M2" in capsys.readouterr().out
    _review(root)
    assert _cli(["handoff", "status", "--repo-root", str(root)]) == 0   # the sweep lists it too
    out = capsys.readouterr().out
    assert "M2: approved" in out and "mark-implementation-reviewed M2 sets it Complete" in out


def test_approval_through_mark_implementation_reviewed_releases_the_rollup(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path)
    tip = git(root, "rev-parse", "dev")
    assert _mir(root, "M2", "--yes") == 1   # no record yet: --yes never creates one
    assert _statuses(root)["M2"] == "Not Started"
    _review(root)
    assert _mir(root, "M2", "--yes") == 0
    assert _statuses(root)["M2"] == "Complete"
    assert git(root, "status", "--porcelain") == ""
    body = git(root, "log", "-1", "--format=%B")
    assert "M2 full review approved; status -> Complete" in body
    assert f"Reviewed-by: human (human) approve {tip}" in body
    assert "roadmap.md" in git(root, "show", "--name-only", "--format=", "HEAD")
    assert _cli(["handoff", "status", "M2", "--repo-root", str(root)]) == 0
    assert "M2: complete_no_claim" in capsys.readouterr().out
    assert _effective_rollup(root, "M2") == "Complete"  # the closure commit must not reopen the hold
    commit_file(root, "src/later.py", "print('later')\n", "later work on integration")
    assert _effective_rollup(root, "M2") == "Complete"
    assert _statuses(root)["M2"] == "Complete"


def test_mark_implementation_reviewed_refuses_a_leaf_id_and_an_open_milestone(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path, land=False)
    assert _mir(root, "M2.1", "--yes") == 1
    assert "not a milestone" in capsys.readouterr().err
    assert _mir(root, "M2", "--yes") == 1
    assert "unfinished leaves" in capsys.readouterr().err


def test_an_approval_before_the_last_leaf_lands_never_releases_the_hold(tmp_path: Path, capsys) -> None:
    """Sol's regression: the tip approved after alpha covers less than the milestone; beta is still on its branch."""
    root = make_milestone_repo(tmp_path, land=False)
    land_leaf(root, "M2.1")
    _review(root)   # approves dev as it stands: alpha only
    branch_leaf(root, "M2.2")   # finish-this-task runs here, before the merge
    assert complete_rolled_up_ancestors(root, "M2.2") == []
    assert _statuses(root)["M2"] == "Not Started"
    assert "[hold] M2 rolled up to Complete but its leaves M2.2 have not landed on refs/heads/dev" in capsys.readouterr().out
    merge_leaf(root, "M2.2")   # landed: the old approval is for an earlier commit
    assert complete_rolled_up_ancestors(root, "M2.2") == []
    assert "its full review is not approved at refs/heads/dev" in capsys.readouterr().out
    _review(root)   # a fresh review of the landed tip
    assert complete_rolled_up_ancestors(root, "M2.2") == ["roadmap/phases/M2.json"]
    assert _statuses(root)["M2"] == "Complete"


def test_an_unfinished_milestone_is_not_awaiting_its_full_review(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path, land=False)
    land_leaf(root, "M2.1")
    branch_leaf(root, "M2.2")
    reviews_dir(root, "M2").mkdir(parents=True)
    assert _cli(["handoff", "status", "M2", "--repo-root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "M2: leaves_open" in out and "leaves M2.2 are not Complete at refs/heads/dev" in out
    assert "awaiting_full_review" not in out
    with pytest.raises(SystemExit):
        rp.build_packet(root, "M2", ref=None, verify_cmds=[])
    assert "leaves M2.2 are not Complete" in capsys.readouterr().err
    notes = tmp_path / "notes.md"
    _review(root, model="human")
    notes.write_text(reviews_dir(root, "M2").joinpath("REVIEW-human.md").read_text().replace("human", "sol"))
    assert _cli(["review", "record", "M2", "--model", "sol", "--verdict", "approve", "--file", str(notes),
                 "--repo-root", str(root)]) == 1
    assert "leaves M2.2 are not Complete" in capsys.readouterr().err


def test_close_refuses_on_the_wrong_branch(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path)
    _review(root)
    git(root, "checkout", "-q", "-b", "other", "dev")
    assert _mir(root, "M2", "--yes") == 1
    assert "the checked-out branch is 'other', not the integration branch 'dev'" in capsys.readouterr().err
    assert _statuses(root)["M2"] == "Not Started"
    assert git(root, "rev-parse", "other") == git(root, "rev-parse", "dev")


def test_close_refuses_a_divergent_integration_tip(tmp_path: Path, capsys) -> None:
    """The gate is read at the remote-tracking tip; a local dev ahead of it must not close the milestone."""
    root = make_milestone_repo(tmp_path)
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(root), str(bare))
    git(root, "remote", "add", "origin", str(bare))
    git(root, "fetch", "-q", "origin")
    reviewed = git(root, "rev-parse", "origin/dev")
    _review(root, commit=reviewed)
    commit_file(root, "src/local.py", "print('local')\n", "local work past the reviewed tip")
    assert resolve_target(root, "M2").commit == reviewed
    assert _mir(root, "M2", "--yes") == 1
    assert f"HEAD ({git(root, 'rev-parse', 'HEAD')[:12]}) is not the reviewed commit {reviewed[:12]}" in \
        capsys.readouterr().err
    assert _statuses(root)["M2"] == "Not Started"
    assert "local work past" in git(root, "log", "-1", "--format=%s")
