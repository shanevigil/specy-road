"""``do-next-available-task`` refuses a second claim in a checkout that already holds one.

M11.63. With one leaf claimed and its branch present, pickup registered, pushed
and switched to a second leaf with exit 0, so one checkout silently owned two.
It now exits 6 naming the held claim before changing anything, unless
``--allow-second-claim``. A claim whose branch is gone, or whose branch another
worktree has checked out, is not this checkout's and does not block.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from tests.test_baseline_gate_cli import FEATURE, SHEET, _branches, _git, _pickup, _project

from specy_road.agents_md_block import render_agents_lines
from specy_road.bundled_scripts.do_next_task_args import parse_do_next_task_args
from specy_road.bundled_scripts.planning_artifacts import expected_planning_rel

SECOND = "feature/rm-leaf-two"


def _two_leaves(tmp_path: Path) -> Path:
    """:func:`_project` plus a second authored leaf ``M2``, pushed."""
    root = _project(tmp_path)
    chunk = root / "roadmap" / "phases" / "M1.json"
    nodes = json.loads(chunk.read_text())["nodes"]
    node = {
        **nodes[0], "id": "M2", "node_key": str(uuid.uuid5(uuid.NAMESPACE_URL, "M2")),
        "codename": "leaf-two", "title": "Leaf two", "sibling_order": 2,
    }
    node["planning_dir"] = expected_planning_rel(node)
    (root / node["planning_dir"]).write_text(SHEET, encoding="utf-8")
    chunk.write_text(json.dumps({"nodes": [*nodes, node]}))
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "second leaf")
    _git(root, "push", "-q", "origin", "main")
    return root


def _registry(root: Path, ref: str) -> str:
    return _git(root, "show", f"{ref}:roadmap/registry.yaml")


def test_second_pickup_exits_6_naming_the_held_claim_and_claims_nothing(tmp_path: Path) -> None:
    root = _two_leaves(tmp_path)
    assert _pickup(root).returncode == 0
    assert _git(root, "branch", "--show-current") == FEATURE
    main_before = _git(root, "rev-parse", "main")
    r = _pickup(root)
    assert r.returncode == 6, r.stderr
    assert f"already holds a claim on M1 ({FEATURE})" in r.stderr
    assert "--allow-second-claim" in r.stderr and "abort-task-pickup" in r.stderr
    assert _git(root, "branch", "--show-current") == FEATURE
    assert _git(root, "rev-parse", "main") == main_before
    assert _git(root, "rev-parse", "origin/main") == main_before
    assert "leaf-two" not in _registry(root, "main")
    assert SECOND not in _branches(root)


def test_allow_second_claim_picks_up_the_next_leaf(tmp_path: Path) -> None:
    root = _two_leaves(tmp_path)
    assert _pickup(root).returncode == 0
    r = _pickup(root, "--allow-second-claim")
    assert r.returncode == 0, r.stderr
    assert _git(root, "branch", "--show-current") == SECOND
    assert "leaf-one" in _registry(root, "origin/main") and "leaf-two" in _registry(root, "origin/main")


def test_a_claim_whose_branch_is_gone_does_not_block(tmp_path: Path) -> None:
    root = _two_leaves(tmp_path)
    assert _pickup(root).returncode == 0
    _git(root, "checkout", "-q", "main")
    _git(root, "branch", "-q", "-D", FEATURE)
    r = _pickup(root)
    assert r.returncode == 0, r.stderr
    assert "already holds a claim" not in r.stderr
    assert _git(root, "branch", "--show-current") == SECOND


def test_claims_checked_out_in_other_worktrees_are_theirs_not_this_checkouts(tmp_path: Path) -> None:
    root = _two_leaves(tmp_path)
    assert _pickup(root, "--worktree").returncode == 0
    r = _pickup(root, "--worktree")
    assert r.returncode == 0, r.stderr
    assert _git(root, "branch", "--show-current") == "main"
    assert _git(root / "work" / ".worktrees" / "leaf-two", "branch", "--show-current") == SECOND


def test_the_agents_md_stub_describes_pickups_exit_6_and_its_override() -> None:
    line = next(ln for ln in render_agents_lines() if "**When nothing is pickable:**" in ln)
    assert "exit `6` is a claim this checkout holds" in line
    assert "`--allow-second-claim`" in line and "`--resume-in-flight` (grind)" in line
    assert parse_do_next_task_args(["--allow-second-claim"]).allow_second_claim
