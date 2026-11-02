"""Rules the CLI already enforces are one-line pointers in the managed blocks (M5.4).

Every sentence taken out of a block is listed here with the pointer that replaced
it and the test that proves the CLI enforces it, so no rule is dropped silently.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.agent_guide_block import render_guide_lines
from specy_road.agents_md_block import injected_context, render_agents_lines
from specy_road.init_project import run_init_project

REPO = Path(__file__).resolve().parent.parent
AGENTS = "\n".join(render_agents_lines())
CLAUDE = "\n".join(render_guide_lines())

#: (block, removed sentence, pointer that replaced it, ``tests/<file>::<test>`` that enforces it)
REMOVED = [
    (AGENTS, "syncs the integration branch, registers (rows record `owner`), pushes, then creates `feature/rm-*`.",
     "claims a leaf, pushes the claim, then creates `feature/rm-*`",
     "tests/test_do_next_task_pickup.py::test_pickup_git_order_pushes_by_default"),
    (AGENTS, "`--local` skips sync and push (claim invisible until you push); prefer the default.",
     "`--local` skips the sync and push, so no one else sees the claim; prefer the default.",
     "tests/test_claim_traps.py::test_local_pickup_skips_sync_and_push"),
    (AGENTS, "The target is always a leaf; ancestors only roll up progress.", "claims a leaf",
     "tests/test_do_next_task_pickup.py::test_pickup_rejects_non_leaf_when_available_returns_parent"),
    (AGENTS, "the node is `Complete` and the claim released on the feature branch only, until the PR merges.",
     "the leaf is `Complete` only on its feature branch until the PR merges",
     "tests/test_do_next_finished_unmerged.py::test_finished_leaf_on_unmerged_branch_is_dropped"),
    (AGENTS, "do not re-pick: pickup refuses a leaf whose `feature/rm-*` branch marks it `Complete`.",
     "pickup will not re-pick it",
     "tests/test_do_next_finished_unmerged.py::test_drop_finished_unmerged_filters_and_reports"),
    (AGENTS, "`status: Blocked` leaves are offered first.", "Pickup decides what is ready and in what order (`Blocked` first",
     "tests/test_do_next_queue.py::test_available_prioritizes_blocked_before_not_started"),
    (AGENTS, "`execution_milestone` is advisory; only a `type: gate` dependency keeps work out of the queue.",
     "only a `type: gate` dependency holds work back, never `execution_milestone`",
     "tests/test_do_next_gate.py::test_available_gate_incomplete_blocks_descendant_leaf"),
    (AGENTS, "A dependency on a phase or milestone is satisfied by its rollup (every leaf descendant `Complete`), "
     "not by its own `status`.", "a phase dependency is met by its rollup",
     "tests/test_dependency_rollup_satisfaction.py::test_stale_parent_own_status_no_longer_blocks_a_dependent_leaf"),
    (AGENTS, "After Blocked and MR-rejected, auto-pick follows outline (tree) order, not chunk order;",
     "then outline order",
     "tests/test_do_next_queue.py::test_available_orders_eligible_by_outline_not_merged_chunk_order"),
    (AGENTS, "`--interactive` chooses by number, `--under <NODE_ID>` scopes to a subtree.",
     "choose with `--interactive` or `--under <NODE_ID>`",
     "tests/test_do_next_queue.py::test_pick_interactive_blocked_row_selectable_by_id"),
    (AGENTS, "the interactive human approval in `mark-implementation-reviewed` is the one exception "
     "(default human-only policy).", "`mark-implementation-reviewed` refuses without the reviews",
     "tests/test_mark_implementation_reviewed_gate.py::test_interactive_human_approval_files_a_record"),
    (AGENTS, "Never `mark-implementation-reviewed --yes` on your own work; it refuses without a recorded review.",
     "`mark-implementation-reviewed` refuses without the reviews",
     "tests/test_mark_implementation_reviewed_gate.py::test_yes_without_reviews_refuses"),
    (AGENTS, "Policy: `roadmap/orchestration.yaml`.", "the reviews `roadmap/orchestration.yaml` requires",
     "tests/test_mark_implementation_reviewed_gate.py::test_human_cannot_stand_in_for_a_missing_second_family"),
    (CLAUDE, "Register the claim on the integration branch, then work on `feature/rm-<codename>`.",
     "`specy-road do-next-available-task` registers the claim, then creates `feature/rm-<codename>`",
     "tests/test_do_next_task_pickup.py::test_pickup_git_order_after_sync"),
    (CLAUDE, "The branch name comes from the node's `codename`;",
     "creates `feature/rm-<codename>`", "tests/test_do_next_task_pickup.py::test_pickup_git_order_after_sync"),
]


def _flat(text: str) -> str:
    """Wrapping-blind: the ``CLAUDE.md`` block breaks sentences across lines."""
    return " ".join(text.split())


@pytest.mark.parametrize(("block", "removed", "pointer", "enforced_by"), REMOVED,
                         ids=[r[1][:40] for r in REMOVED])
def test_each_removed_sentence_is_a_pointer_to_an_enforcement_point(
        block: str, removed: str, pointer: str, enforced_by: str) -> None:
    text = _flat(block)
    assert _flat(removed) not in text
    assert _flat(pointer) in text
    path, name = enforced_by.split("::")
    assert f"def {name}(" in (REPO / path).read_text(encoding="utf-8"), enforced_by


#: What the context meter reported for a fresh ``init project`` section before M5.4.
_BEFORE_LINES, _BEFORE_BYTES = 52, 7679


def test_the_meter_reports_a_shorter_section_than_before(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "no-home"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    run_init_project(tmp_path)
    codex, _claude = injected_context(tmp_path)
    section = next(f for f in codex if f.rel == "AGENTS.md")
    assert section.block_lines < _BEFORE_LINES and section.block_size < _BEFORE_BYTES
