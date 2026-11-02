"""A milestone gets one full review of its combined change before it is marked complete (M11.13).

``policy.milestone_full_review`` (default on) holds the ancestor rollup when the
last leaf under a milestone finishes; ``review-packet <MILESTONE_ID>`` diffs from
the first leaf's branch point to the integration tip; approval through
``mark-implementation-reviewed <MILESTONE_ID>`` sets the milestone Complete.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from tests.helpers import DOGFOOD
from tests.review_repo_helpers import commit_file, git

from specy_road.bundled_scripts import mark_implementation_reviewed as mir
from specy_road.bundled_scripts import review_cli
from specy_road.bundled_scripts import review_packet as rp
from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk
from specy_road.finish_ancestor_rollup import complete_rolled_up_ancestors
from specy_road.review_files import reviews_dir
from specy_road.review_target import resolve_target

KEYS = {"M2": "50000000-0000-4000-8000-000000000001", "M2.1": "50000000-0000-4000-8000-000000000002",
        "M2.2": "50000000-0000-4000-8000-000000000003"}
LEAVES = {"M2.1": "alpha", "M2.2": "beta"}
POLICY_OFF = "version: 1\npolicy: {milestone_full_review: false}\n"


def _node(nid: str, parent: str | None, kind: str, codename: str | None = None) -> dict:
    slug = codename or "unnamed"
    return {"id": nid, "node_key": KEYS[nid], "parent_id": parent, "type": kind, "title": f"Node {nid}",
            "planning_dir": f"planning/{nid}_{slug}_{KEYS[nid]}.md", "status": "Not Started",
            "touch_zones": ["src"], "dependencies": [], **({"codename": codename} if codename else {})}


def _chunk(root: Path) -> Path:
    return root / "roadmap" / "phases" / "M2.json"


def _statuses(root: Path) -> dict[str, str]:
    return {n["id"]: n["status"] for n in load_json_chunk(_chunk(root))}


def _set_status(root: Path, nid: str, status: str) -> None:
    nodes = load_json_chunk(_chunk(root))
    next(n for n in nodes if n["id"] == nid)["status"] = status
    _chunk(root).write_text(json.dumps({"nodes": nodes}, indent=2) + "\n", encoding="utf-8")


def _branch_leaf(root: Path, nid: str) -> None:
    """Pickup-shaped branch for ``nid``: register, implement, complete; left checked out, not merged."""
    codename = LEAVES[nid]
    git(root, "checkout", "-q", "-b", f"feature/rm-{codename}", "dev")
    commit_file(root, "roadmap/registry.yaml", f"version: 1\nentries: []\n# {codename}\n",
                f"chore(rm-{codename}): register as in-progress")
    commit_file(root, f"src/{codename}.py", f"print({codename!r})\n", f"feat({codename}): implement")
    _set_status(root, nid, "Complete")
    git(root, "add", "roadmap/phases/M2.json")
    git(root, "commit", "-qm", f"chore(rm-{codename}): complete, deregister")


def _merge_leaf(root: Path, nid: str) -> None:
    git(root, "checkout", "-q", "dev")
    git(root, "merge", "-q", "--no-ff", "--no-edit", f"feature/rm-{LEAVES[nid]}")


def _land_leaf(root: Path, nid: str) -> None:
    _branch_leaf(root, nid)
    _merge_leaf(root, nid)


def make_milestone_repo(tmp_path: Path, *, orchestration: str | None = None, land: bool = True) -> Path:
    """``dev`` with phase ``M2`` over leaves ``M2.1`` and ``M2.2``, both landed unless ``land`` is false."""
    root = tmp_path / "r"
    (root / "roadmap" / "phases").mkdir(parents=True)
    git(root, "init", "-q", "-b", "dev")
    git(root, "config", "user.email", "t@e.com")
    git(root, "config", "user.name", "T")
    shutil.copytree(DOGFOOD / "schemas", root / "schemas")
    nodes = [_node("M2", None, "phase"), _node("M2.1", "M2", "task", "alpha"), _node("M2.2", "M2", "task", "beta")]
    (root / "roadmap" / "manifest.json").write_text(json.dumps({"version": 1, "includes": ["phases/M2.json"]}))
    _chunk(root).write_text(json.dumps({"nodes": nodes}, indent=2) + "\n", encoding="utf-8")
    for n in nodes:
        sheet = root / n["planning_dir"]
        sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.write_text(f"# {n['id']}\n\n## Intent\n\nDo it.\n\n## References\n", encoding="utf-8")
    (root / "roadmap" / "git-workflow.yaml").write_text(
        "version: 1\nintegration_branch: dev\nremote: origin\nrequire_implementation_review_before_finish: true\n")
    (root / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n")
    if orchestration is not None:
        (root / "roadmap" / "orchestration.yaml").write_text(orchestration)
    (root / ".gitignore").write_text("work/reviews/\n.specyrd/\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "graph")
    if land:
        for nid in LEAVES:
            _land_leaf(root, nid)
    return root


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
        _set_status(root, nid, "Complete")
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


def test_mark_implementation_reviewed_refuses_a_leaf_id_and_an_open_milestone(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path, land=False)
    assert _mir(root, "M2.1", "--yes") == 1
    assert "not a milestone" in capsys.readouterr().err
    assert _mir(root, "M2", "--yes") == 1
    assert "unfinished leaves" in capsys.readouterr().err


def test_an_approval_before_the_last_leaf_lands_never_releases_the_hold(tmp_path: Path, capsys) -> None:
    """Sol's regression: the tip approved after alpha covers less than the milestone; beta is still on its branch."""
    root = make_milestone_repo(tmp_path, land=False)
    _land_leaf(root, "M2.1")
    _review(root)   # approves dev as it stands: alpha only
    _branch_leaf(root, "M2.2")   # finish-this-task runs here, before the merge
    assert complete_rolled_up_ancestors(root, "M2.2") == []
    assert _statuses(root)["M2"] == "Not Started"
    assert "[hold] M2 rolled up to Complete but its leaves M2.2 have not landed on refs/heads/dev" in capsys.readouterr().out
    _merge_leaf(root, "M2.2")   # landed: the old approval is for an earlier commit
    assert complete_rolled_up_ancestors(root, "M2.2") == []
    assert "its full review is not approved at refs/heads/dev" in capsys.readouterr().out
    _review(root)   # a fresh review of the landed tip
    assert complete_rolled_up_ancestors(root, "M2.2") == ["roadmap/phases/M2.json"]
    assert _statuses(root)["M2"] == "Complete"


def test_an_unfinished_milestone_is_not_awaiting_its_full_review(tmp_path: Path, capsys) -> None:
    root = make_milestone_repo(tmp_path, land=False)
    _land_leaf(root, "M2.1")
    _branch_leaf(root, "M2.2")
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
