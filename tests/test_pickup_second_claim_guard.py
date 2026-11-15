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

from tests.support.extracted.baseline_gate_cli import branches, git
from tests.support.pickup import (
    FEATURE,
    SHEET,
    make_pickup_project as project,
    run_pickup as pickup,
    run_specy_road as run,
)

from specy_road.agents_md_block import render_rules
from specy_road.bundled_scripts.do_next_task_args import parse_do_next_task_args
from specy_road.planning_artifacts import expected_planning_rel
import pytest

SECOND = "feature/rm-leaf-two"


def _two_leaves(tmp_path: Path) -> Path:
    """:func:`project` plus a second authored leaf ``M2``, pushed."""
    root = project(tmp_path)
    chunk = root / "roadmap" / "phases" / "M1.json"
    nodes = json.loads(chunk.read_text())["nodes"]
    node = {
        **nodes[0], "id": "M2", "node_key": str(uuid.uuid5(uuid.NAMESPACE_URL, "M2")),
        "codename": "leaf-two", "title": "Leaf two", "sibling_order": 2,
    }
    node["planning_dir"] = expected_planning_rel(node)
    (root / node["planning_dir"]).write_text(SHEET, encoding="utf-8")
    chunk.write_text(json.dumps({"nodes": [*nodes, node]}))
    git(root, "add", "-A")
    git(root, "commit", "-qm", "second leaf")
    git(root, "push", "-q", "origin", "main")
    return root


def _registry(root: Path, ref: str) -> str:
    return git(root, "show", f"{ref}:roadmap/registry.yaml")


@pytest.mark.slow
def test_second_pickup_exits_6_naming_the_held_claim_and_claims_nothing(tmp_path: Path) -> None:
    root = _two_leaves(tmp_path)
    assert pickup(root).returncode == 0
    assert git(root, "branch", "--show-current") == FEATURE
    main_before = git(root, "rev-parse", "main")
    r = pickup(root)
    assert r.returncode == 6, r.stderr
    assert f"already holds a claim on M1 ({FEATURE})" in r.stderr
    assert "--allow-second-claim" in r.stderr and "abort-task-pickup" in r.stderr
    assert git(root, "branch", "--show-current") == FEATURE
    assert git(root, "rev-parse", "main") == main_before
    assert git(root, "rev-parse", "origin/main") == main_before
    assert "leaf-two" not in _registry(root, "main")
    assert SECOND not in branches(root)


@pytest.mark.slow
def test_allow_second_claim_picks_up_the_next_leaf(tmp_path: Path) -> None:
    root = _two_leaves(tmp_path)
    assert pickup(root).returncode == 0
    r = pickup(root, "--allow-second-claim")
    assert r.returncode == 0, r.stderr
    assert git(root, "branch", "--show-current") == SECOND
    assert "leaf-one" in _registry(root, "origin/main") and "leaf-two" in _registry(root, "origin/main")


@pytest.mark.slow
def test_a_claim_whose_branch_is_gone_does_not_block(tmp_path: Path) -> None:
    root = _two_leaves(tmp_path)
    assert pickup(root).returncode == 0
    git(root, "checkout", "-q", "main")
    git(root, "branch", "-q", "-D", FEATURE)
    r = pickup(root)
    assert r.returncode == 0, r.stderr
    assert "already holds a claim" not in r.stderr
    assert git(root, "branch", "--show-current") == SECOND


@pytest.mark.slow
def test_claims_checked_out_in_other_worktrees_are_theirs_not_this_checkouts(tmp_path: Path) -> None:
    root = _two_leaves(tmp_path)
    assert pickup(root, "--worktree").returncode == 0
    r = pickup(root, "--worktree")
    assert r.returncode == 0, r.stderr
    assert git(root, "branch", "--show-current") == "main"
    assert git(root / "work" / ".worktrees" / "leaf-two", "branch", "--show-current") == SECOND


@pytest.mark.slow
def test_a_leaf_finished_in_pr_mode_does_not_block_the_next_pickup(tmp_path: Path) -> None:
    """``pr`` finish releases the row on the feature branch only; ``main`` keeps it until the PR merges."""
    root = _two_leaves(tmp_path)
    assert run(root, "do-next-available-task", "--on-complete", "pr").returncode == 0
    (root / "src").mkdir()
    (root / "src" / "one.txt").write_text("leaf one\n", encoding="utf-8")
    git(root, "add", "src/one.txt")
    git(root, "commit", "-qm", "leaf one work")
    fin = run(root, "finish-this-task", "--on-complete", "pr")
    assert fin.returncode == 0, fin.stderr
    git(root, "checkout", "-q", "main")
    assert "leaf-one" in _registry(root, "main")
    r = run(root, "do-next-available-task", "--on-complete", "pr")
    assert r.returncode == 0, r.stderr
    assert "already holds a claim" not in r.stderr
    assert git(root, "branch", "--show-current") == SECOND
    assert "leaf-two" in _registry(root, "origin/main")


def test_the_agent_rules_describe_pickups_exit_6_and_its_override() -> None:
    line = next(ln for ln in render_rules().splitlines() if "**When nothing is pickable:**" in ln)
    assert "exit `6` is a claim this checkout holds" in line
    assert "`--allow-second-claim`" in line and "`--resume-in-flight` (grind)" in line
    assert parse_do_next_task_args(["--allow-second-claim"]).allow_second_claim
