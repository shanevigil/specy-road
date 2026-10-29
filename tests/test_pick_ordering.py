"""Opt-in ``--prefer-agentic`` pickup order (M4.9): picker, config, plan, grind pass-through."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts import do_next_available as dna
from specy_road.bundled_scripts import do_next_task as dnt
from specy_road.bundled_scripts import grind_session as gs
from specy_road.bundled_scripts.do_next_task_args import parse_do_next_task_args
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.bundled_scripts.session_plan import compute_session_plan, session_plan_to_dict
from specy_road.bundled_scripts.session_plan_git import gather_session_plan
from specy_road.bundled_scripts.session_plan_render import render_session_plan_text
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


def _ids(nodes: list[dict]) -> list[str]:
    return [n["id"] for n in nodes]


def _write_git_workflow(root: Path, **extra) -> None:
    (root / "roadmap").mkdir(parents=True, exist_ok=True)
    lines = ["version: 1", "integration_branch: dev", "remote: origin"]
    lines += [f"{k}: {str(v).lower()}" for k, v in extra.items()]
    (root / "roadmap" / "git-workflow.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Picker
# ---------------------------------------------------------------------------


def test_default_order_is_outline_regardless_of_execution_milestone() -> None:
    assert _ids(dna._available(_mixed_nodes(), _EMPTY_REG, {})) == ["M1", "M2", "M3", "M4", "M5"]


def test_prefer_agentic_orders_agentic_mixed_unset_human_then_outline() -> None:
    got = dna._available(_mixed_nodes(), _EMPTY_REG, {}, prefer_agentic=True)
    assert _ids(got) == ["M4", "M5", "M3", "M2", "M1"]


def test_prefer_agentic_keeps_the_blocked_tier_first() -> None:
    nodes = _mixed_nodes()
    nodes[0]["status"] = "Blocked"  # M1, Human-led
    got = dna._available(nodes, _EMPTY_REG, {}, prefer_agentic=True)
    assert _ids(got) == ["M1", "M4", "M5", "M3", "M2"]


def test_prefer_agentic_does_not_change_eligibility() -> None:
    nodes = _mixed_nodes()
    nodes[3]["status"] = "Complete"  # M4
    default = set(_ids(dna._available(nodes, _EMPTY_REG, {})))
    preferred = set(_ids(dna._available(nodes, _EMPTY_REG, {}, prefer_agentic=True)))
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


@pytest.mark.parametrize(
    ("cli", "yaml_value", "expected"),
    [([], True, True), ([], None, False), (["--no-prefer-agentic"], True, False)],
)
def test_pickup_hands_the_resolved_setting_to_the_picker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cli, yaml_value, expected
) -> None:
    """``main`` reads the flag, else git-workflow.yaml, and passes it to ``_available``."""
    if yaml_value is not None:
        _write_git_workflow(tmp_path, prefer_agentic_pick_order=yaml_value)
    (tmp_path / "roadmap").mkdir(exist_ok=True)
    (tmp_path / "roadmap" / "registry.yaml").write_text("version: 1\nentries: []\n", encoding="utf-8")
    seen: list[bool] = []

    def recording_available(nodes, reg, enrich=None, **kwargs):
        seen.append(kwargs.get("prefer_agentic", False))
        return dna._available(nodes, reg, enrich, **kwargs)

    class _Picked(Exception):
        pass

    def stop_at_pick(_args, _nodes, _reg, available, _statuses):
        raise _Picked(available[0]["id"])

    monkeypatch.setattr(dnt, "load_roadmap", lambda _p: {"nodes": _mixed_nodes()})
    monkeypatch.setattr(dnt, "_available", recording_available)
    monkeypatch.setattr(dnt, "_load_branch_enrichment", lambda _r: {})
    monkeypatch.setattr(dnt, "sync_integration_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(dnt, "_assert_current_branch_equals", lambda _b: None)
    monkeypatch.setattr(dnt, "_pick_node", stop_at_pick)

    with pytest.raises(_Picked) as picked:
        dnt.main(["--repo-root", str(tmp_path), *cli])

    # seen[0] is the pre-sync emptiness check, which never orders anything.
    assert seen[-1] is expected
    assert str(picked.value) == ("M4" if expected else "M1")


def test_grind_passes_an_explicit_setting_through_to_pickup(tmp_path: Path) -> None:
    for argv, flag in (
        (["--prefer-agentic"], "--prefer-agentic"),
        (["--no-prefer-agentic"], "--no-prefer-agentic"),
    ):
        args = parse_grind_session_args(["--plan", *argv])
        assert flag in gs._pickup_args(args, tmp_path)
    unset = gs._pickup_args(parse_grind_session_args(["--plan"]), tmp_path)
    assert not any("prefer-agentic" in a for a in unset)


# ---------------------------------------------------------------------------
# Session plan
# ---------------------------------------------------------------------------


def test_plan_ready_order_equals_pickup_order_and_carries_execution() -> None:
    nodes = _mixed_nodes()
    for prefer in (False, True):
        plan = compute_session_plan(nodes, _EMPTY_REG, prefer_agentic=prefer)
        assert plan.ready == _ids(dna._available(nodes, _EMPTY_REG, prefer_agentic=prefer))
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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


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
