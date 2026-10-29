"""Opt-in ``--prefer-agentic`` pickup order (M4.9): picker, config, plan, grind pass-through."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.helpers import DOGFOOD

from specy_road.bundled_scripts import do_next_task as dnt
from specy_road.bundled_scripts.do_next_task_args import parse_do_next_task_args
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args, pickup_args
from specy_road.bundled_scripts.session_plan import compute_session_plan
from specy_road.bundled_scripts.session_plan_git import gather_session_plan
from specy_road.bundled_scripts.session_plan_render import render_session_plan_text, session_plan_to_dict
from specy_road.git_workflow_config import resolve_prefer_agentic, validate_git_workflow_dict

_EMPTY_REG = {"version": 1, "entries": []}


def _leaf(nid: str, order: int, execution: str | None, *, status: str = "Not Started") -> dict:
    node = {
        "id": nid,
        "node_key": f"{order:08d}-0000-4000-8000-000000000000",
        "type": "task",
        "title": nid,
        "codename": f"cn-{order}",
        "status": status,
        "dependencies": [],
        "parent_id": None,
        "sibling_order": order,
        "touch_zones": [],
    }
    if execution is not None:
        node["execution_milestone"] = execution
    return node


def _mixed_nodes() -> list[dict]:
    """Outline order M1..M5 deliberately puts Human-led and unset ahead of Agentic-led."""
    return [
        _leaf("M1", 1, "Human-led"),
        _leaf("M2", 2, None),
        _leaf("M3", 3, "Mixed"),
        _leaf("M4", 4, "Agentic-led"),
        _leaf("M5", 5, "Agentic-led"),
    ]


def _ready(nodes: list[dict], **kwargs) -> list[str]:
    """The pickup queue, through the public plan API (``ready`` is ``_available``'s order)."""
    return compute_session_plan(nodes, _EMPTY_REG, **kwargs).ready


def _write_git_workflow(root: Path, **extra) -> None:
    (root / "roadmap").mkdir(parents=True, exist_ok=True)
    lines = ["version: 1", "integration_branch: dev", "remote: origin"]
    lines += [f"{k}: {str(v).lower()}" for k, v in extra.items()]
    (root / "roadmap" / "git-workflow.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Picker
# ---------------------------------------------------------------------------


def test_default_order_is_outline_regardless_of_execution_milestone() -> None:
    assert _ready(_mixed_nodes()) == ["M1", "M2", "M3", "M4", "M5"]


def test_prefer_agentic_orders_agentic_mixed_unset_human_then_outline() -> None:
    assert _ready(_mixed_nodes(), prefer_agentic=True) == ["M4", "M5", "M3", "M2", "M1"]


def test_prefer_agentic_keeps_the_blocked_tier_first() -> None:
    nodes = _mixed_nodes()
    nodes[0]["status"] = "Blocked"  # M1, Human-led
    assert _ready(nodes, prefer_agentic=True) == ["M1", "M4", "M5", "M3", "M2"]


def test_prefer_agentic_does_not_change_eligibility() -> None:
    nodes = _mixed_nodes()
    nodes[3]["status"] = "Complete"  # M4
    default = set(_ready(nodes))
    preferred = set(_ready(nodes, prefer_agentic=True))
    assert preferred == default == {"M1", "M2", "M3", "M5"}


# ---------------------------------------------------------------------------
# Config + CLI
# ---------------------------------------------------------------------------


def test_schema_accepts_prefer_agentic_pick_order() -> None:
    data = {"version": 1, "integration_branch": "dev", "remote": "origin"}
    assert validate_git_workflow_dict({**data, "prefer_agentic_pick_order": True}) is None
    assert validate_git_workflow_dict({**data, "prefer_agentic_pick_order": "yes"}) is not None


def test_resolve_prefer_agentic_cli_beats_yaml_beats_default(tmp_path: Path) -> None:
    assert resolve_prefer_agentic(tmp_path, cli=None) is False
    _write_git_workflow(tmp_path, prefer_agentic_pick_order=True)
    assert resolve_prefer_agentic(tmp_path, cli=None) is True
    assert resolve_prefer_agentic(tmp_path, cli=False) is False
    _write_git_workflow(tmp_path, prefer_agentic_pick_order=False)
    assert resolve_prefer_agentic(tmp_path, cli=True) is True


@pytest.mark.parametrize(
    ("argv", "expected"),
    [([], None), (["--prefer-agentic"], True), (["--no-prefer-agentic"], False)],
)
def test_do_next_and_grind_parse_the_flag(argv: list[str], expected) -> None:
    assert parse_do_next_task_args(argv).prefer_agentic is expected
    assert parse_grind_session_args(["--plan", *argv]).prefer_agentic is expected


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return r.stdout.strip()


def _pickup_repo(tmp_path: Path, yaml_value: bool | None) -> Path:
    """Two authored root leaves on ``dev``: ``M1`` (Human-led) before ``M2`` (Agentic-led)."""
    root = tmp_path / "r"
    (root / "roadmap" / "phases").mkdir(parents=True)
    shutil.copytree(DOGFOOD / "schemas", root / "schemas")
    nodes = []
    for order, (nid, codename, execution) in enumerate(
        (("M1", "human", "Human-led"), ("M2", "agent", "Agentic-led")), 1
    ):
        key = f"{order}{order}{order}{order}{order}{order}{order}{order}-1111-5111-8111-111111111111"
        planning_dir = f"planning/{nid}_{codename}_{key}.md"
        nodes.append({
            "id": nid, "node_key": key, "codename": codename, "title": codename,
            "type": "task", "parent_id": None, "sibling_order": order,
            "status": "Not Started", "dependencies": [], "touch_zones": ["src"],
            "execution_milestone": execution, "acceptance": ["it works"],
            "planning_dir": planning_dir,
        })
        (root / planning_dir).parent.mkdir(exist_ok=True)
        (root / planning_dir).write_text(f"# {nid}\n\n## Intent\n\nWork.\n", encoding="utf-8")
    (root / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M.json"]}), encoding="utf-8"
    )
    (root / "roadmap" / "phases" / "M.json").write_text(json.dumps({"nodes": nodes}), encoding="utf-8")
    (root / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n", encoding="utf-8")
    extra = {} if yaml_value is None else {"prefer_agentic_pick_order": yaml_value}
    _write_git_workflow(root, **extra)
    _git(tmp_path, "init", "-q", "-b", "dev", str(root))
    _git(root, "config", "user.email", "t@e.com")
    _git(root, "config", "user.name", "T")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "graph")
    return root


@pytest.mark.parametrize(
    ("cli", "yaml_value", "expected"),
    [
        ([], None, "M1"),
        (["--prefer-agentic"], None, "M2"),
        ([], True, "M2"),
        (["--no-prefer-agentic"], True, "M1"),
    ],
)
def test_pickup_claims_by_the_resolved_setting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cli, yaml_value, expected
) -> None:
    """``--local`` pickup reads the flag, else git-workflow.yaml, and claims accordingly."""
    repo = _pickup_repo(tmp_path, yaml_value)
    monkeypatch.setattr(dnt, "ROOT", repo)
    try:
        dnt.main(["--local", "--on-complete", "merge", "--repo-root", str(repo), *cli])
    except SystemExit as e:
        assert (e.code or 0) == 0
    row = yaml.safe_load(_git(repo, "show", "dev:roadmap/registry.yaml"))["entries"][0]
    assert row["node_id"] == expected


def test_grind_passes_an_explicit_setting_through_to_pickup(tmp_path: Path) -> None:
    for argv, flag in (
        (["--prefer-agentic"], "--prefer-agentic"),
        (["--no-prefer-agentic"], "--no-prefer-agentic"),
    ):
        args = parse_grind_session_args(["--plan", *argv])
        assert flag in pickup_args(args, tmp_path)
    unset = pickup_args(parse_grind_session_args(["--plan"]), tmp_path)
    assert not any("prefer-agentic" in a for a in unset)


# ---------------------------------------------------------------------------
# Session plan
# ---------------------------------------------------------------------------


def test_plan_carries_execution_for_every_ready_leaf() -> None:
    nodes = _mixed_nodes()
    for prefer in (False, True):
        plan = compute_session_plan(nodes, _EMPTY_REG, prefer_agentic=prefer)
        assert plan.ready_execution == {
            "M1": "Human-led", "M2": None, "M3": "Mixed",
            "M4": "Agentic-led", "M5": "Agentic-led",
        }
        assert session_plan_to_dict(plan)["prefer_agentic"] is prefer


def test_plan_text_shows_execution_milestone_beside_next_auto_pick() -> None:
    nodes = _mixed_nodes()
    text = render_session_plan_text(compute_session_plan(nodes, _EMPTY_REG, prefer_agentic=True))
    assert "**Next auto-pick:** `M4` (Agentic-led)" in text
    assert "prefer_agentic_pick_order" in text

    text = render_session_plan_text(compute_session_plan(nodes[1:2], _EMPTY_REG))
    assert "**Next auto-pick:** `M2` (no execution milestone)" in text
    assert "prefer_agentic_pick_order" not in text


def test_gather_session_plan_reads_the_yaml_default(tmp_path: Path) -> None:
    """``grind-session --plan`` with no flag follows git-workflow.yaml, as pickup does."""
    roadmap = tmp_path / "roadmap"
    (roadmap / "phases").mkdir(parents=True)
    (roadmap / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M.json"]}), encoding="utf-8"
    )
    (roadmap / "phases" / "M.json").write_text(
        json.dumps({"nodes": _mixed_nodes()}), encoding="utf-8"
    )
    (roadmap / "registry.yaml").write_text("version: 1\nentries: []\n", encoding="utf-8")
    _write_git_workflow(tmp_path, prefer_agentic_pick_order=True)
    _git(tmp_path, "init", "-q", "-b", "dev")

    _n, _r, plan = gather_session_plan(tmp_path, None, allow_unauthored=True)
    assert plan.prefer_agentic is True
    assert plan.ready[0] == "M4"

    _n, _r, plan = gather_session_plan(
        tmp_path, None, allow_unauthored=True, prefer_agentic=False
    )
    assert plan.ready[0] == "M1"
