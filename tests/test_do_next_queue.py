"""Tests for do-next queue, interactive picker, and empty-queue diagnostics."""

from __future__ import annotations

import pytest

import do_next_available as dna
import do_next_task as dnt
import do_next_task_interactive as dnti

# dependencies[] reference node_key UUIDs (not display ids)
_NK_PREREQ = "11111111-1111-4111-8111-111111111111"
_NK_EXAMPLE = "22222222-2222-4222-8222-222222222222"

_BASE_NODE = {
    "id": "M1.1",
    "node_key": _NK_EXAMPLE,
    "type": "milestone",
    "title": "Example",
    "codename": "example",
    "execution_milestone": "Agentic-led",
    "status": "Not Started",
    "dependencies": [],
    "touch_zones": [],
}


def _reg(*node_ids: str) -> dict:
    return {
        "version": 1,
        "entries": [{"node_id": nid, "codename": nid} for nid in node_ids],
    }


def test_available_returns_unclaimed_agentic() -> None:
    nodes = [_BASE_NODE]
    result = dnt._available(nodes, _reg(), {})
    assert len(result) == 1
    assert result[0]["id"] == "M1.1"


def test_available_picks_leaf_not_parent_when_descendant_is_ready() -> None:
    parent = {
        "id": "M1",
        "node_key": "99999999-9999-4999-8999-999999999999",
        "type": "phase",
        "title": "Parent",
        "codename": "parent-node",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": [],
    }
    leaf = {
        **_BASE_NODE,
        "id": "M1.1",
        "parent_id": "M1",
        "codename": "leaf-node",
    }
    result = dnt._available([parent, leaf], _reg(), {})
    assert [n["id"] for n in result] == ["M1.1"]


def test_available_excludes_claimed() -> None:
    nodes = [_BASE_NODE]
    assert dnt._available(nodes, _reg("M1.1"), {}) == []


def test_available_excludes_complete() -> None:
    node = {**_BASE_NODE, "status": "Complete"}
    assert dnt._available([node], _reg(), {}) == []


def test_available_excludes_unmet_deps() -> None:
    # The dependent leaf (M1.1) is blocked because its dependency (M1.0) is
    # not yet Complete. M1.0 itself is eligible (all leaves are agentic per
    # F-003/F-007); the assertion is that M1.1 is NOT returned.
    dep = {
        "id": "M1.0",
        "node_key": _NK_PREREQ,
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "dependencies": [],
    }
    node = {**_BASE_NODE, "dependencies": [_NK_PREREQ]}
    result = dnt._available([dep, node], _reg(), {})
    assert "M1.1" not in [n["id"] for n in result]


def test_available_includes_when_deps_complete() -> None:
    dep = {
        "id": "M1.0",
        "node_key": _NK_PREREQ,
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Complete",
        "dependencies": [],
    }
    node = {**_BASE_NODE, "dependencies": [_NK_PREREQ]}
    result = dnt._available([dep, node], _reg(), {})
    assert len(result) == 1


def test_available_includes_human_led_now_that_all_leaves_are_agentic() -> None:
    # Per F-003/F-007, every leaf is considered agentic by design regardless
    # of execution_milestone. This used to be excluded; now it's included.
    node = {**_BASE_NODE, "execution_milestone": "Human-led"}
    result = dnt._available([node], _reg(), {})
    assert [n["id"] for n in result] == ["M1.1"]


def test_available_excludes_no_codename() -> None:
    # A leaf without a codename is still not eligible (validate auto-heals,
    # but if a node slips through without one, do-next will not pick it).
    node = {**_BASE_NODE, "codename": None}
    assert dnt._available([node], _reg(), {}) == []


def test_available_prioritizes_blocked_before_not_started() -> None:
    a = {**_BASE_NODE, "id": "M1.2", "codename": "a", "status": "Not Started"}
    b = {
        **_BASE_NODE,
        "id": "M1.3",
        "node_key": "33333333-3333-4333-8333-333333333333",
        "codename": "b",
        "status": "Blocked",
    }
    result = dnt._available([a, b], _reg(), {})
    assert [n["id"] for n in result] == ["M1.3", "M1.2"]


def test_load_branch_enrichment_returns_empty_on_registry_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    def boom(_root):
        raise RuntimeError("no registry")

    monkeypatch.setattr(dna, "load_registry", boom)
    assert dna._load_branch_enrichment(tmp_path) == {}


def test_available_orders_blocked_then_mr_rejected_then_not_started() -> None:
    a = {**_BASE_NODE, "id": "M1.2", "codename": "a", "status": "Not Started"}
    b = {
        **_BASE_NODE,
        "id": "M1.3",
        "node_key": "33333333-3333-4333-8333-333333333333",
        "codename": "b",
        "status": "Blocked",
    }
    c = {
        **_BASE_NODE,
        "id": "M1.4",
        "node_key": "44444444-4444-4444-8444-444444444444",
        "codename": "c",
        "status": "In Progress",
    }
    enrich = {
        "M1.4": {"kind": "github_pr", "pr_state": "rejected", "merged": False},
    }
    result = dnt._available([a, b, c], _reg(), enrich)
    assert [n["id"] for n in result] == ["M1.3", "M1.4", "M1.2"]


def test_available_prioritizes_mr_rejected_before_not_started() -> None:
    a = {**_BASE_NODE, "id": "M1.2", "codename": "a", "status": "Not Started"}
    b = {
        **_BASE_NODE,
        "id": "M1.3",
        "node_key": "33333333-3333-4333-8333-333333333333",
        "codename": "b",
        "status": "In Progress",
    }
    enrich = {
        "M1.3": {"kind": "github_pr", "pr_state": "rejected", "merged": False},
    }
    result = dnt._available([a, b], _reg(), enrich)
    assert [n["id"] for n in result] == ["M1.3", "M1.2"]


def test_available_orders_eligible_by_outline_not_merged_chunk_order() -> None:
    """Merged JSON array order must not beat sibling_order / tree pre-order."""
    nk_root = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    nk_first_in_chunk = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    nk_second_in_chunk = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    root = {
        "id": "M0",
        "node_key": nk_root,
        "type": "phase",
        "title": "Phase",
        "parent_id": None,
        "sibling_order": 0,
        "status": "Complete",
        "dependencies": [],
    }
    first_in_array = {
        "id": "M0.1",
        "node_key": nk_first_in_chunk,
        "parent_id": "M0",
        "sibling_order": 1,
        "type": "milestone",
        "title": "Later outline",
        "codename": "later-outline",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": [],
    }
    second_in_array = {
        "id": "M0.2",
        "node_key": nk_second_in_chunk,
        "parent_id": "M0",
        "sibling_order": 0,
        "type": "milestone",
        "title": "Earlier outline",
        "codename": "earlier-outline",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": [],
    }
    nodes = [root, first_in_array, second_in_array]
    result = dnt._available(nodes, _reg(), {})
    assert [n["id"] for n in result] == ["M0.2", "M0.1"]


def test_pick_interactive_blocked_row_selectable_by_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dep = {
        "id": "M1.0",
        "node_key": _NK_PREREQ,
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "dependencies": [],
    }
    leaf = {
        **_BASE_NODE,
        "id": "M1.1",
        "dependencies": [_NK_PREREQ],
        "touch_zones": ["z"],
    }
    blocked = [(leaf, [_NK_PREREQ])]
    monkeypatch.setattr("builtins.input", lambda _prompt: "M1.1")
    picked = dnti.pick_interactive([], [dep, leaf], blocked_entries=blocked)
    assert picked["id"] == "M1.1"
    err = capsys.readouterr().err
    assert "dependency-blocked" in err


def test_pick_interactive_rejects_parent_selection(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parent = {
        "id": "M1",
        "node_key": "99999999-9999-4999-8999-999999999999",
        "type": "phase",
        "title": "Parent",
        "codename": "parent-node",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": [],
    }
    leaf = {
        **_BASE_NODE,
        "id": "M1.1",
        "parent_id": "M1",
        "codename": "leaf-node",
    }
    answers = iter(["M1", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    picked = dnti.pick_interactive([leaf], [parent, leaf])
    assert picked["id"] == "M1.1"
    err = capsys.readouterr().err
    assert "Cannot claim parent node" in err


def test_exit_no_actionable_leaves_has_deterministic_diagnostics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parent = {
        "id": "M2",
        "node_key": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        "type": "phase",
        "title": "Parent",
        "codename": "parent-node",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": [],
    }
    leaf = {
        **_BASE_NODE,
        "id": "M2.1",
        "parent_id": "M2",
        "codename": "leaf-node",
    }
    with pytest.raises(SystemExit) as ei:
        dnt._exit_no_actionable_leaves(
            [parent, leaf],
            _reg("M2.1"),
            after_sync=False,
        )
    assert ei.value.code == 1
    err = capsys.readouterr().err
    assert "No actionable leaf tasks available (before sync)." in err
    assert "blocked by unmet dependencies: none" in err
    assert "already claimed leaves: M2.1" in err
    assert "open leaves (dependency-satisfied, unclaimed): none" in err
