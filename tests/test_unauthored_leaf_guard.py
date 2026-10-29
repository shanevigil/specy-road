"""Pickup, ``grind-session --plan`` and ``validate`` refuse unauthored leaves.

Unauthored: the node has no ``acceptance`` and its planning sheet still carries
text the toolkit wrote itself (scaffold-planning's section bodies, or brainstorm
promote's "Rewrite this section…" line). An agent handed such a leaf has
nothing to build from.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from tests.helpers import SCHEMAS

from specy_road.bundled_scripts import do_next_task as dnt
from specy_road.bundled_scripts.brainstorm_promote import seed_planning_sheet
from specy_road.bundled_scripts.brainstorm_session import Idea
from specy_road.bundled_scripts.grind_session import run_session
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.bundled_scripts.planning_artifacts import expected_planning_rel
from specy_road.bundled_scripts.planning_sheet_bootstrap import (
    placeholder_sheet,
    render_feature_sheet_template,
)
from specy_road.bundled_scripts.session_plan import compute_session_plan
from specy_road.bundled_scripts.session_plan_render import render_session_plan_text, session_plan_to_dict
from specy_road.bundled_scripts.validate_roadmap import validate_at

FILLED = (
    "## Intent\n\nThe export writes one row per node.\n\n"
    "## Approach\n\nExtend the writer; a golden file test proves it.\n\n"
    "## Tasks / checklist\n\n- [ ] …\n\n## References\n\n- Roadmap chunk for `{nid}`\n"
)


def _node(nid: str, order: int, **over) -> dict:
    n = {
        "id": nid,
        "node_key": str(uuid.uuid5(uuid.NAMESPACE_URL, nid)),
        "codename": f"leaf-{order}",
        "title": f"Leaf {order}",
        "type": "task",
        "parent_id": None,
        "sibling_order": order,
        "status": "Not Started",
        "dependencies": [],
        "touch_zones": ["src"],
    }
    n.update(over)
    n["planning_dir"] = expected_planning_rel(n)
    return n


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path, sheets: dict[str, str], **over: dict) -> tuple[Path, list[dict]]:
    """One task leaf per ``sheets`` entry (id -> sheet text, or ``"scaffold"``)."""
    root = tmp_path / "r"
    (root / "roadmap" / "phases").mkdir(parents=True)
    shutil.copytree(SCHEMAS, root / "schemas")
    nodes = [_node(nid, i, **over.get(nid, {})) for i, nid in enumerate(sheets, 1)]
    for n in nodes:
        text = sheets[n["id"]]
        sheet = root / n["planning_dir"]
        sheet.parent.mkdir(parents=True, exist_ok=True)
        sheet.write_text(
            render_feature_sheet_template(n["id"]) if text == "scaffold" else text.format(nid=n["id"]),
            encoding="utf-8",
        )
    rm = root / "roadmap"
    (rm / "manifest.json").write_text(json.dumps({"version": 1, "includes": ["phases/M1.json"]}))
    (rm / "phases" / "M1.json").write_text(json.dumps({"nodes": nodes}))
    (rm / "registry.yaml").write_text("version: 1\nentries: []\n")
    (rm / "git-workflow.yaml").write_text("version: 1\nintegration_branch: main\nremote: origin\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@e.com")
    _git(root, "config", "user.name", "T")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "graph")
    return root, nodes


def _promote(root: Path, node: dict) -> None:
    seed_planning_sheet(root, node, Idea(id="i-1", title="Faster export", rationale="Users wait."))


# --- placeholder_sheet ------------------------------------------------------


def test_scaffolded_sheet_is_a_placeholder(tmp_path: Path) -> None:
    root, nodes = _repo(tmp_path, {"M1": "scaffold"})
    reason = placeholder_sheet(root, nodes[0])
    assert reason is not None
    assert nodes[0]["planning_dir"] in reason
    assert "scaffold-planning's placeholder under ## Intent" in reason
    assert "no acceptance criteria" in reason


def test_promote_skeleton_is_a_placeholder(tmp_path: Path) -> None:
    root, nodes = _repo(tmp_path, {"M1": "scaffold"})
    _promote(root, nodes[0])
    reason = placeholder_sheet(root, nodes[0])
    assert reason is not None and "brainstorm promote's placeholder under ## Intent" in reason


def test_a_leftover_scaffold_approach_is_a_placeholder(tmp_path: Path) -> None:
    sheet = FILLED.replace("Extend the writer; a golden file test proves it.",
                           "Constraints, major steps, and how you will verify done.")
    root, nodes = _repo(tmp_path, {"M1": sheet})
    reason = placeholder_sheet(root, nodes[0])
    assert reason is not None and "## Approach" in reason


def test_filled_sheet_or_acceptance_is_not_a_placeholder(tmp_path: Path) -> None:
    root, nodes = _repo(tmp_path, {"M1": FILLED, "M2": "scaffold"},
                        M2={"acceptance": ["one row per node"]})
    assert placeholder_sheet(root, nodes[0]) is None
    assert placeholder_sheet(root, nodes[1]) is None


def test_missing_sheet_is_not_reported_here(tmp_path: Path) -> None:
    root, nodes = _repo(tmp_path, {"M1": "scaffold"})
    (root / nodes[0]["planning_dir"]).unlink()
    assert placeholder_sheet(root, nodes[0]) is None


# --- A1: do-next-available-task ---------------------------------------------


class _Picked(Exception):
    pass


def _pick(monkeypatch: pytest.MonkeyPatch, root: Path, *argv: str) -> str:
    """Run pickup up to the point it announces its choice; return that node id."""
    monkeypatch.setattr(dnt, "sync_integration_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(dnt, "prompt_on_complete", lambda _root, _cli: "merge")

    def stop(node, _branch, _root):
        raise _Picked(node["id"])

    monkeypatch.setattr(dnt, "print_pickup_header", stop)
    with pytest.raises(_Picked) as picked:
        dnt.main(["--repo-root", str(root), *argv])
    return picked.value.args[0]


def test_pickup_skips_an_unauthored_leaf_and_says_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    root, nodes = _repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    assert _pick(monkeypatch, root) == "M2"
    err = capsys.readouterr().err
    assert f"skipping M1: {nodes[0]['planning_dir']} still has scaffold-planning's placeholder" in err
    assert "--allow-unauthored" in err


def test_pickup_skips_a_promote_skeleton(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    root, nodes = _repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    _promote(root, nodes[0])
    _git(root, "commit", "-qam", "promote")
    assert _pick(monkeypatch, root) == "M2"
    assert "skipping M1:" in capsys.readouterr().err


def test_allow_unauthored_picks_it_anyway(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    root, _nodes = _repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    assert _pick(monkeypatch, root, "--allow-unauthored") == "M1"
    assert "skipping" not in capsys.readouterr().err


def test_filled_sheet_or_acceptance_is_picked_as_before(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root, _nodes = _repo(tmp_path, {"M1": "scaffold", "M2": FILLED}, M1={"acceptance": ["works"]})
    assert _pick(monkeypatch, root) == "M1"


def test_nothing_but_unauthored_leaves_exits_with_the_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    root, _nodes = _repo(tmp_path, {"M1": "scaffold"})
    monkeypatch.setattr(dnt, "sync_integration_branch", lambda *_a, **_k: None)
    with pytest.raises(SystemExit) as e:
        dnt.main(["--repo-root", str(root)])
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "skipping M1:" in err
    assert "No actionable leaf tasks available (after sync)." in err


# --- A2: grind-session --plan -----------------------------------------------


def _plan(root: Path, *argv: str) -> None:
    run_session(parse_grind_session_args(["--plan", "--json", "--repo-root", str(root), *argv]))


def test_plan_lists_unauthored_leaves_as_not_ready(tmp_path: Path, capsys) -> None:
    root, nodes = _repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    capsys.readouterr()
    _plan(root)
    plan = json.loads(capsys.readouterr().out.splitlines()[0])
    assert plan["ready"] == ["M2"]
    assert [u["node_id"] for u in plan["unauthored"]] == ["M1"]
    assert nodes[0]["planning_dir"] in plan["unauthored"][0]["reason"]
    assert plan["totals"]["unauthored"] == 1
    assert plan["parallel_batches"] == [["M2"]]


def test_plan_allow_unauthored_makes_them_ready(tmp_path: Path, capsys) -> None:
    root, _nodes = _repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    capsys.readouterr()
    _plan(root, "--allow-unauthored")
    plan = json.loads(capsys.readouterr().out.splitlines()[0])
    assert plan["ready"] == ["M1", "M2"]
    assert plan["unauthored"] == []
    assert "unauthored" not in plan["totals"]


def test_plan_text_names_the_reason(tmp_path: Path, capsys) -> None:
    root, nodes = _repo(tmp_path, {"M1": "scaffold"})
    capsys.readouterr()
    run_session(parse_grind_session_args(["--plan", "--repo-root", str(root)]))
    out = capsys.readouterr().out
    assert "**Not ready — placeholder planning sheet, no acceptance" in out
    assert f"- `M1`: {nodes[0]['planning_dir']} still has" in out


def test_an_unauthored_leaf_keeps_its_dependents_in_the_waves() -> None:
    a = _node("M1", 1)
    b = _node("M2", 2, dependencies=[a["node_key"]])
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
    capsys.readouterr()
    validate_at(root, no_overlap_warn=True, require_registry=True, **kw)
    out = capsys.readouterr()
    assert "OK: roadmap and registry validate." in out.out
    return out.err


def test_validate_prints_one_block_naming_every_unauthored_leaf(tmp_path: Path, capsys) -> None:
    root, nodes = _repo(tmp_path, {"M1": "scaffold", "M2": FILLED, "M3": "scaffold"})
    err = _validate_err(root, capsys)
    assert err.count("open leaf/leaves have a placeholder planning sheet") == 1
    assert "warning: 2 open leaf/leaves" in err
    assert f"  M1: {nodes[0]['planning_dir']}" in err
    assert "  M3: " in err
    assert "  M2: " not in err


def test_validate_caps_the_block_and_all_lists_every_one(tmp_path: Path, capsys) -> None:
    root, _nodes = _repo(tmp_path, {f"M{i}": "scaffold" for i in range(1, 14)})
    capped = _validate_err(root, capsys)
    assert "warning: 13 open leaf/leaves" in capped
    assert sum(ln.startswith("  M") for ln in capped.splitlines()) == 10
    assert "… and 3 more (specy-road validate --all lists every one)" in capped
    every = _validate_err(root, capsys, show_all=True)
    assert sum(ln.startswith("  M") for ln in every.splitlines()) == 13
    assert "… and" not in every


def test_validate_is_silent_for_authored_or_closed_leaves(tmp_path: Path, capsys) -> None:
    root, _nodes = _repo(tmp_path, {"M1": FILLED, "M2": "scaffold", "M3": "scaffold"},
                         M2={"acceptance": ["works"]}, M3={"status": "Complete"})
    assert "placeholder planning sheet" not in _validate_err(root, capsys)
