"""Milestone session and chunk IO, through the public entry points."""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts import start_milestone_session
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.milestone_chunk_io import (
    maybe_promote_milestone_to_pending_mr,
    write_milestone_execution,
)
from specy_road.milestone_rollup_git import branch_exists, current_branch
from specy_road.milestone_session import milestone_session_path, read_milestone_session
from tests.milestone_repo_helpers import make_milestone_repo
from tests.review_repo_helpers import git
from tests.scenarios.milestone.repos import (
    CODENAME,
    INTEGRATION,
    PARENT,
    ROLLUP,
    active_execution,
    landed_milestone,
    milestone_repo,
    parent_node,
)


def test_start_milestone_session_creates_the_rollup_branch(tmp_path: Path) -> None:
    """The session command creates ``feature/rm-<codename>`` from integration."""
    root = milestone_repo(tmp_path, land=False)
    start_milestone_session.main(
        [PARENT, "--repo-root", str(root), "--base", INTEGRATION, "--remote", "origin"]
    )

    assert branch_exists(root, ROLLUP)
    assert current_branch(root) == INTEGRATION
    assert git(root, "rev-parse", ROLLUP) == git(root, "rev-parse", INTEGRATION)
    session = read_milestone_session(milestone_session_path(root / "work"))
    assert session is not None
    assert session.parent_node_id == PARENT
    assert session.parent_codename == CODENAME
    assert session.rollup_branch == ROLLUP
    assert session.integration_branch == INTEGRATION
    execution = parent_node(root)["milestone_execution"]
    assert execution["state"] == "active"
    assert execution["rollup_branch"] == ROLLUP
    assert execution["integration_branch"] == INTEGRATION
    assert execution["remote"] == "origin"


def test_write_milestone_execution_stores_the_active_lock(tmp_path: Path) -> None:
    """``write_milestone_execution`` persists the lock and leaves it valid."""
    root = make_milestone_repo(tmp_path, land=False)
    doc = active_execution()
    chunk = write_milestone_execution(root, PARENT, doc)

    assert chunk == root / "roadmap" / "phases" / "M2.json"
    execution = parent_node(root)["milestone_execution"]
    assert execution["state"] == "active"
    assert execution["rollup_branch"] == ROLLUP
    assert execution["integration_branch"] == INTEGRATION
    assert execution["remote"] == "origin"
    assert execution["opened_at"]


def test_promotion_stays_put_while_a_leaf_is_open(tmp_path: Path) -> None:
    """An open leaf keeps the milestone ``active``."""
    root = make_milestone_repo(tmp_path, land=False)
    write_milestone_execution(root, PARENT, active_execution())

    promoted = maybe_promote_milestone_to_pending_mr(
        root, PARENT, load_roadmap(root)["nodes"]
    )

    assert promoted is False
    assert parent_node(root)["milestone_execution"]["state"] == "active"


def test_promotion_sets_pending_mr_when_every_leaf_is_complete(tmp_path: Path) -> None:
    """Every structural leaf Complete moves an active milestone to ``pending_mr``."""
    root = landed_milestone(tmp_path, state="active")

    promoted = maybe_promote_milestone_to_pending_mr(
        root, PARENT, load_roadmap(root)["nodes"]
    )

    assert promoted is True
    assert parent_node(root)["milestone_execution"]["state"] == "pending_mr"
