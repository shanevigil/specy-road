"""M11.11: pickup, ``grind-session --plan`` and ``orchestrate plan`` agree on ready.

All three take ready leaves from ``do_next_available._available`` and drop the
unauthored ones (``planning_sheet_bootstrap.placeholder_sheet``); ``orchestrate
plan`` used to skip the second step and staff leaves pickup refuses.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tests.unauthored_repo_helpers import FILLED, pick_leaf, plan_json, unauthored_repo

from specy_road.bundled_scripts import orchestrate_cli
from specy_road.orchestrate_plan import build_orchestration_plan


def test_pickup_grind_plan_and_orchestrate_plan_agree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    root, _nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED, "M3": FILLED},
                         M2={"touch_zones": ["a"]}, M3={"touch_zones": ["b"]})
    capsys.readouterr()
    plan_json(root)
    grind = json.loads(capsys.readouterr().out.splitlines()[0])
    orch, err = build_orchestration_plan(root, today=date(2026, 11, 1))
    assert err is None and orch is not None
    orch_ready = [a.node_id for batch in orch.batches for a in batch]

    assert grind["ready"] == orch_ready == ["M2", "M3"]
    assert [u["node_id"] for u in grind["unauthored"]] == orch.unauthored == ["M1"]
    assert pick_leaf(monkeypatch, root) == orch_ready[0]


def test_orchestrate_plan_names_the_leaves_pickup_skips(tmp_path: Path, capsys) -> None:
    root, _nodes = unauthored_repo(tmp_path, {"M1": "scaffold", "M2": FILLED})
    with pytest.raises(SystemExit):
        orchestrate_cli.main(["orchestrate", "plan", "--today", "2026-11-01", "--repo-root", str(root)])
    out = capsys.readouterr().out
    assert "  M2" in out and "  M1" not in out
    assert "unauthored (not assigned; pickup skips them): M1" in out
    with pytest.raises(SystemExit):
        orchestrate_cli.main(["orchestrate", "plan", "--json", "--today", "2026-11-01", "--repo-root", str(root)])
    assert json.loads(capsys.readouterr().out)["unauthored"] == ["M1"]
