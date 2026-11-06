"""Rules the CLI or the tool-call guard enforces are one-line pointers in the agent rules (M5.4).

Every sentence taken out of a block is listed here with the pointer that replaced
it and the test that proves the CLI enforces it, so no rule is dropped silently.
The rules moved to ``.specyrd/AGENTS.md`` on 2026-11-04; the rows that pinned the
``CLAUDE.md`` block now pin the ``AGENTS.md`` stub, which carries those core rules.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.agents_md_block import CLAUDE_MD_TARGET_LINES, injected_context, render_agents_lines, render_rules
from specy_road.init_project import run_init_project

REPO = Path(__file__).resolve().parent.parent
AGENTS = render_rules()
STUB = "\n".join(render_agents_lines())

#: (block, removed text, pointer that carries its fact now, ``tests/<file>::<test>`` that enforces it).
#: One row per fact, so a pointer that drops a qualifier fails its own row.
REMOVED = [
    (AGENTS, "registers (rows record `owner`), pushes, then creates `feature/rm-*`.",
     "syncs the integration branch, claims a leaf, never an ancestor (the row records `owner`), pushes the claim, "
     "then creates `feature/rm-*`", "tests/test_do_next_task_pickup.py::test_pickup_git_order_pushes_by_default"),
    (AGENTS, "(rows record `owner`)", "(the row records `owner`)",
     "tests/test_claim_traps.py::test_claim_row_carries_owner"),
    (AGENTS, "`--local` skips sync and push (claim invisible until you push);",
     "`--local` skips the sync and push, so no one else sees the claim; prefer the default.",
     "tests/test_claim_traps.py::test_local_pickup_skips_sync_and_push"),
    (AGENTS, "The target is always a leaf; ancestors only roll up progress.", "claims a leaf, never an ancestor",
     "tests/test_do_next_task_pickup.py::test_pickup_rejects_non_leaf_when_available_returns_parent"),
    (AGENTS, "the node is `Complete` and the claim released on the feature branch only, until the PR merges.",
     "the leaf is `Complete` and its claim released only on its feature branch until the PR merges",
     "tests/test_do_next_finished_unmerged.py::test_finished_leaf_on_unmerged_branch_is_dropped"),
    (AGENTS, "do not re-pick: pickup refuses a leaf whose `feature/rm-*` branch marks it `Complete`.",
     "pickup will not re-pick it",
     "tests/test_do_next_finished_unmerged.py::test_drop_finished_unmerged_filters_and_reports"),
    (AGENTS, "`status: Blocked` leaves are offered first.", "Pickup decides what is ready and in what order (`Blocked` first",
     "tests/test_do_next_queue.py::test_available_prioritizes_blocked_before_not_started"),
    (AGENTS, "After Blocked and MR-rejected,", "`Blocked` first, then MR-rejected, then outline order",
     "tests/test_do_next_queue.py::test_available_orders_blocked_then_mr_rejected_then_not_started"),
    (AGENTS, "auto-pick follows outline (tree) order, not chunk order;", "then outline order, not chunk order",
     "tests/test_do_next_queue.py::test_available_orders_eligible_by_outline_not_merged_chunk_order"),
    (AGENTS, "`execution_milestone` is advisory;", "never `execution_milestone`",
     "tests/test_pick_ordering.py::test_default_order_is_outline_regardless_of_execution_milestone"),
    (AGENTS, "only a `type: gate` dependency keeps work out of the queue.",
     "only a `type: gate` dependency holds work back",
     "tests/test_do_next_gate.py::test_available_gate_incomplete_blocks_descendant_leaf"),
    (AGENTS, "A dependency on a phase or milestone is satisfied by its rollup (every leaf descendant `Complete`), "
     "not by its own `status`.",
     "a phase or milestone dependency is met when every leaf under it is `Complete`, not by its own `status`",
     "tests/test_dependency_rollup_satisfaction.py::test_stale_parent_own_status_no_longer_blocks_a_dependent_leaf"),
    (AGENTS, "`--interactive` chooses by number,", "choose by number with `--interactive`",
     "tests/test_do_next_queue.py::test_pick_interactive_blocked_row_selectable_by_id"),
    (AGENTS, "`--under <NODE_ID>` scopes to a subtree.", "scope to a subtree with `--under <NODE_ID>`",
     "tests/test_do_next_queue.py::test_exit_no_leaves_under_parent_also_names_the_branch"),
    (AGENTS, "Never `mark-implementation-reviewed --yes` on your own work; it refuses without a recorded review.",
     "Never `mark-implementation-reviewed --yes` on your own work: it refuses without the reviews",
     "tests/test_mark_implementation_reviewed_gate.py::test_yes_without_reviews_refuses"),
    (AGENTS, "Policy: `roadmap/orchestration.yaml`.", "the reviews `roadmap/orchestration.yaml` requires",
     "tests/test_mark_implementation_reviewed_gate.py::test_human_cannot_stand_in_for_a_missing_second_family"),
    (AGENTS, "Commit by explicit path (`git commit --only <paths>`); never `git add -A`, `git commit -a`, or a bare "
     "`git commit` — the index is shared.", "commit only with `git commit --only <paths>`",
     "tests/test_tool_call_guard.py::test_destructive_commands_are_classified"),
    (AGENTS, "Never `stash`, `reset --hard`, `checkout -- .`, `clean`, `rebase`, `commit --amend`, or switch branches",
     "never stash, hard-reset, discard changes, clean, rebase, amend or switch branches in a tree another session "
     "may be using", "tests/test_tool_call_guard.py::test_destructive_commands_are_classified"),
    (AGENTS, "in a tree another session may be using; use your own",
     "The opt-in tool-call guard (`specy-road session guard`) refuses these while another session is live",
     "tests/test_tool_call_guard.py::test_deny_only_with_another_live_session"),
    (STUB, "commit by explicit path, never `-A`/`-a`;",
     "opt-in tool-call guard refuses all of these, and `git add -A`/`commit -a`", "tests/test_tool_call_guard.py::test_destructive_commands_are_classified"),
    (STUB, "no stash, reset, or branch switches here", "`git add -A`/`commit -a`, while another session is live",
     "tests/test_tool_call_guard.py::test_deny_only_with_another_live_session"),
    (STUB, "Register the claim on the integration branch, then work on `feature/rm-<codename>`.",
     "`specy-road do-next-available-task` registers the claim on the integration branch, then creates "
     "`feature/rm-<codename>`", "tests/test_do_next_task_pickup.py::test_pickup_git_order_after_sync"),
    (STUB, "The branch name comes from the node's `codename`;",
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
#: The ``AGENTS.md`` stub that replaced the full section on 2026-11-04 (it was 52 lines, 7,797 bytes then).
#: Codex reads only this, so a rule added to it needs the maintainer's approval and raises these.
#: 17 / 2,063 since the review restored the discard and abort-after-finish rules (2026-11-04).
#: 17 / 2,205 since M21.30 added the CR1 review-policy rule (maintainer-approved, 2026-11-05).
_STUB_LINES, _STUB_BYTES = 17, 2205
#: ``.specyrd/AGENTS.md`` when it was created (2026-11-04): the old section plus the non-Claude part of the
#: old ``CLAUDE.md`` block. Claude Code imports it whole; Codex never reads it.
#: 68 / 9,289 since M21.30 added the CR1 review-policy rule (maintainer-approved, 2026-11-05).
_RULES_LINES, _RULES_BYTES = 68, 9289


def test_the_meter_reports_a_shorter_section_than_before(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "no-home"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    run_init_project(tmp_path)
    codex = injected_context(tmp_path)["Codex"]
    section = next(f for f in codex if f.rel == "AGENTS.md")
    assert section.block_lines < _BEFORE_LINES and section.block_size < _BEFORE_BYTES
    assert section.block_lines <= _STUB_LINES and section.block_size <= _STUB_BYTES
    assert [f.rel for f in codex] == ["AGENTS.md"]   # the rules file costs Codex nothing


def test_the_rules_file_stays_within_its_budget() -> None:
    lines, size = len(AGENTS.splitlines()), len(AGENTS.encode("utf-8"))
    assert lines <= _RULES_LINES and size <= _RULES_BYTES
    assert lines < CLAUDE_MD_TARGET_LINES
