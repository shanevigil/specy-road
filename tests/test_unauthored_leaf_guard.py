"""Pickup, ``grind-session --plan`` and ``validate`` refuse unauthored leaves.

Unauthored for pickup and session plan: the planning sheet still carries
scaffold-planning's or brainstorm promote's placeholder under ``## Intent`` or
``## Approach`` (even when the node has ``acceptance``), or the node has no
``acceptance`` and the sheet is still a placeholder. ``validate`` lists only
the no-``acceptance`` case.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unauthored_repo_helpers import FILLED, git, leaf_node, pick_leaf, plan_json, unauthored_repo

from specy_road.bundled_scripts import do_next_task as dnt
from specy_road.bundled_scripts.brainstorm_promote import seed_planning_sheet
from specy_road.bundled_scripts.brainstorm_session import Idea
from specy_road.bundled_scripts.grind_session import run_session
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.bundled_scripts.planning_sheet_bootstrap import placeholder_sheet
from specy_road.bundled_scripts.session_plan import compute_session_plan, session_plan_to_dict
from specy_road.bundled_scripts.session_plan_render import render_session_plan_text
from specy_road.bundled_scripts.validate_roadmap import main as validate_main, validate_at
from specy_road.planning_scaffold_check import scaffold_sheet


def _promote(root: Path, node: dict) -> None:
    seed_planning_sheet(root, node, Idea(id="i-1", title="Faster export", rationale="Users wait."))


# --- placeholder_sheet ------------------------------------------------------


def test_scaffolded_sheet_is_a_placeholder(tmp_path: Path) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold"})
    reason = placeholder_sheet(root, nodes[0])
    assert reason is not None
    assert nodes[0]["planning_dir"] in reason
    assert "scaffold-planning's placeholder under ## Intent" in reason
    assert "no acceptance criteria" in reason


def test_promote_skeleton_is_a_placeholder(tmp_path: Path) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold"})
    _promote(root, nodes[0])
    reason = placeholder_sheet(root, nodes[0])
    assert reason is not None and "brainstorm promote's placeholder under ## Approach" in reason
    assert scaffold_sheet(root, {**nodes[0], "acceptance": ["works"]}) == (
        f"{nodes[0]['planning_dir']} still has brainstorm promote's placeholder under ## Approach; "
        "`specy-road author-approach M1` prints the prompt to write it"
    )


def test_a_leftover_scaffold_approach_is_a_placeholder(tmp_path: Path) -> None:
    sheet = FILLED.replace("Extend the writer; a golden file test proves it.",
                           "Constraints, major steps, and how you will verify done.")
    root, nodes = unauthored_repo(tmp_path, {"M1": sheet})
    reason = placeholder_sheet(root, nodes[0])
    assert reason is not None and "## Approach" in reason
    assert scaffold_sheet(root, nodes[0]) == (
        f"{nodes[0]['planning_dir']} still has scaffold-planning's placeholder under ## Approach; "
        "`specy-road author-approach M1` prints the prompt to write it"
    )


def test_filled_sheet_or_acceptance_is_not_a_placeholder(tmp_path: Path) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": FILLED, "M2": "scaffold"},
                        M2={"acceptance": ["one row per node"]})
    assert placeholder_sheet(root, nodes[0]) is None
    assert placeholder_sheet(root, nodes[1]) is None
    # M3.14: acceptance does not make the sheet written.
    assert scaffold_sheet(root, nodes[0]) is None
    assert scaffold_sheet(root, nodes[1]) == (
        f"{nodes[1]['planning_dir']} still has scaffold-planning's placeholder under ## Intent"
    )


def test_missing_sheet_is_not_reported_here(tmp_path: Path) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold"})
    (root / nodes[0]["planning_dir"]).unlink()
    assert placeholder_sheet(root, nodes[0]) is None
    assert scaffold_sheet(root, nodes[0]) is None
    assert scaffold_sheet(root, {**nodes[0], "planning_dir": None}) is None


# --- A1: do-next-available-task ---------------------------------------------


def test_pickup_skips_an_unauthored_leaf_and_says_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    assert pick_leaf(monkeypatch, root) == "M2"
    err = capsys.readouterr().err
    assert f"skipping M1: {nodes[0]['planning_dir']} still has scaffold-planning's placeholder" in err
    assert "--allow-unauthored" in err
    assert "warning: picked" not in err


def test_pickup_skips_a_promote_skeleton(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    _promote(root, nodes[0])
    git(root, "commit", "-qam", "promote")
    assert pick_leaf(monkeypatch, root) == "M2"
    assert "skipping M1:" in capsys.readouterr().err


def test_allow_unauthored_picks_it_anyway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    root, _nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    assert pick_leaf(monkeypatch, root, "--allow-unauthored") == "M1"
    assert "skipping" not in capsys.readouterr().err


def test_filled_sheet_or_acceptance_with_scaffold_still_skipped_at_pickup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """M11.15: acceptance does not bypass an unwritten ## Intent / ## Approach."""
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED}, M1={"acceptance": ["works"]})
    assert pick_leaf(monkeypatch, root) == "M2"
    err = capsys.readouterr().err
    assert (f"skipping M1: {nodes[0]['planning_dir']} still has scaffold-planning's "
            "placeholder under ## Intent") in err
    assert "--allow-scaffold-planning" in err
    assert "warning: picked" not in err


def test_allow_scaffold_planning_warns_and_picks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED}, M1={"acceptance": ["works"]})
    assert pick_leaf(monkeypatch, root, "--allow-scaffold-planning") == "M1"
    err = capsys.readouterr().err
    assert "skipping" not in err
    assert (f"warning: picked M1, but {nodes[0]['planning_dir']} still has scaffold-planning's "
            "placeholder under ## Intent") in err


def test_plan_lists_scaffold_approach_with_acceptance_as_unauthored(
    tmp_path: Path, capsys
) -> None:
    sheet = FILLED.replace("Extend the writer; a golden file test proves it.",
                           "Constraints, major steps, and how you will verify done.")
    root, nodes = unauthored_repo(tmp_path, {"M1": sheet, "M2": FILLED}, M1={"acceptance": ["works"]})
    capsys.readouterr()
    plan_json(root)
    plan = json.loads(capsys.readouterr().out.splitlines()[0])
    assert plan["ready"] == ["M2"]
    assert [u["node_id"] for u in plan["unauthored"]] == ["M1"]
    assert "placeholder under ## Approach" in plan["unauthored"][0]["reason"]
    assert nodes[0]["planning_dir"] in plan["unauthored"][0]["reason"]


def test_nothing_but_unauthored_leaves_exits_with_the_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    root, _nodes = unauthored_repo(tmp_path, {"M1": "scaffold"})
    monkeypatch.setattr(dnt, "sync_integration_branch", lambda *_a, **_k: None)
    with pytest.raises(SystemExit) as e:
        dnt.main(["--repo-root", str(root)])
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "skipping M1:" in err
    assert "No actionable leaf tasks available (after sync)." in err


# --- A2: grind-session --plan -----------------------------------------------


def test_plan_lists_unauthored_leaves_as_not_ready(tmp_path: Path, capsys) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    capsys.readouterr()
    plan_json(root)
    plan = json.loads(capsys.readouterr().out.splitlines()[0])
    assert plan["ready"] == ["M2"]
    assert [u["node_id"] for u in plan["unauthored"]] == ["M1"]
    assert nodes[0]["planning_dir"] in plan["unauthored"][0]["reason"]
    assert plan["totals"]["unauthored"] == 1
    assert plan["parallel_batches"] == [["M2"]]


def test_plan_allow_unauthored_makes_them_ready(tmp_path: Path, capsys) -> None:
    root, _nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    capsys.readouterr()
    plan_json(root, "--allow-unauthored")
    plan = json.loads(capsys.readouterr().out.splitlines()[0])
    assert plan["ready"] == ["M1", "M2"]
    assert plan["unauthored"] == []
    assert "unauthored" not in plan["totals"]


def test_plan_allow_unauthored_keeps_acceptance_scaffold_not_ready(
    tmp_path: Path, capsys
) -> None:
    """Pickup --allow-unauthored still skips acceptance + leftover scaffold Approach."""
    sheet = FILLED.replace("Extend the writer; a golden file test proves it.",
                           "Constraints, major steps, and how you will verify done.")
    root, nodes = unauthored_repo(
        tmp_path, {"M1": sheet, "M2": FILLED}, M1={"acceptance": ["works"]}
    )
    capsys.readouterr()
    plan_json(root, "--allow-unauthored")
    plan = json.loads(capsys.readouterr().out.splitlines()[0])
    assert plan["ready"] == ["M2"]
    assert [u["node_id"] for u in plan["unauthored"]] == ["M1"]
    assert "placeholder under ## Approach" in plan["unauthored"][0]["reason"]
    assert nodes[0]["planning_dir"] in plan["unauthored"][0]["reason"]


def test_plan_text_names_the_reason(tmp_path: Path, capsys) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold"})
    capsys.readouterr()
    run_session(parse_grind_session_args(["--plan", "--repo-root", str(root)]))
    out = capsys.readouterr().out
    heading = next(ln for ln in out.splitlines() if ln.startswith("**Not ready"))
    assert heading == "**Not ready — unwritten planning sheet (pickup skips these):**"
    assert f"- `M1`: {nodes[0]['planning_dir']} still has" in out


def test_an_unauthored_leaf_keeps_its_dependents_in_the_waves() -> None:
    a = leaf_node("M1", 1)
    b = leaf_node("M2", 2, dependencies=[a["node_key"]])
    plan = compute_session_plan([a, b], {"version": 1, "entries": []},
                                unauthored={"M1": "placeholder"})
    assert plan.ready == []
    assert [w.node_ids for w in plan.waves] == [["M1"], ["M2"]]
    assert session_plan_to_dict(plan)["unauthored"] == [
        {"node_id": "M1", "codename": "leaf-1", "reason": "placeholder"}
    ]
    assert "- `M1`: placeholder" in render_session_plan_text(plan)


# --- A3: validate -----------------------------------------------------------


def _validate_err(root: Path, capsys, **kw) -> str:
    """stderr of ``validate_at`` with ``strict_authoring``, which keeps the unauthored block a warning (M11.46)."""
    capsys.readouterr()
    validate_at(root, no_overlap_warn=True, require_registry=True, strict_authoring=True, **kw)
    out = capsys.readouterr()
    assert "OK: roadmap and registry validate." in out.out
    return out.err


def test_validate_prints_one_block_naming_every_unauthored_leaf(tmp_path: Path, capsys) -> None:
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED, "M3": "scaffold"})
    err = _validate_err(root, capsys)
    assert err.count("open leaf/leaves have a placeholder planning sheet") == 1
    assert "warning: 2 open leaf/leaves" in err
    assert f"  M1: {nodes[0]['planning_dir']}" in err
    assert "  M3: " in err
    assert "  M2: " not in err


def test_validate_caps_the_block_and_all_lists_every_one(tmp_path: Path, capsys) -> None:
    root, _nodes = unauthored_repo(tmp_path, {f"M{i}": "scaffold" for i in range(1, 14)})
    capped = _validate_err(root, capsys)
    assert "warning: 13 open leaf/leaves" in capped
    assert sum(ln.startswith("  M") for ln in capped.splitlines()) == 10
    assert "… and 3 more (specy-road validate --all lists every one)" in capped
    every = _validate_err(root, capsys, show_all=True)
    assert sum(ln.startswith("  M") for ln in every.splitlines()) == 13
    assert "… and" not in every


def test_validate_without_strict_authoring_makes_the_block_a_stdout_notice(tmp_path: Path, capsys) -> None:
    """M11.46: an unauthored leaf is planning in progress; neither block names it on stderr."""
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    capsys.readouterr()
    validate_at(root, no_overlap_warn=True, require_registry=True)
    out, err = capsys.readouterr()
    assert "notice: 1 open leaf/leaves have a placeholder planning sheet" in out
    assert f"  M1: {nodes[0]['planning_dir']}" in out
    assert "M1" not in err


def test_validate_is_silent_for_authored_or_closed_leaves(tmp_path: Path, capsys) -> None:
    root, _nodes = unauthored_repo(tmp_path, {"M1": FILLED, "M2": "scaffold", "M3": "scaffold"},
                         M2={"acceptance": ["works"]}, M3={"status": "Complete"})
    assert "placeholder planning sheet" not in _validate_err(root, capsys)


@pytest.mark.parametrize("show_all", [False, True])
def test_validate_notes_complete_leaves_still_on_the_scaffold(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys, show_all: bool
) -> None:
    """M3.14: one stdout notice (not a stderr warning) counting them; --all lists them."""
    done = {"status": "Complete"}
    root, nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED, "M3": "scaffold", "M4": "scaffold"},
                        M1=done, M2=done, M3={**done, "acceptance": ["works"]})
    argv = ["validate", "--repo-root", str(root), *(["--all"] if show_all else [])]
    monkeypatch.setattr("sys.argv", argv)
    capsys.readouterr()
    validate_main()
    out, err = capsys.readouterr()
    hint = "" if show_all else " (specy-road validate --all lists them)"
    assert sum("still the scaffold" in line for line in out.splitlines() if line.startswith("notice:")) == 1
    assert f"notice: 2 Complete leaf/leaves have a planning sheet that is still the scaffold{hint}." in out
    assert "still the scaffold" not in err
    # Open M4's unauthored notice is on stdout too (M11.46); list only what follows the Complete notice.
    listed = [ln for ln in out.split("Complete leaf/leaves", 1)[1].splitlines() if ln.startswith("  M")]
    assert listed == ([f"  M1: {nodes[0]['planning_dir']} still has scaffold-planning's placeholder under ## Intent",
                       f"  M3: {nodes[2]['planning_dir']} still has scaffold-planning's placeholder under ## Intent"]
                      if show_all else [])
