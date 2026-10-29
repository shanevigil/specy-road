"""`grind-session --plan` and `orchestrate plan` keep ready leaves whose touch
zones overlap out of the same parallel batch."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from specy_road import orchestrate_plan as op
from specy_road.bundled_scripts import session_plan_git
from specy_road.bundled_scripts.session_plan import compute_session_plan
from specy_road.bundled_scripts.session_plan_render import (
    render_session_plan_text,
    session_plan_to_dict,
    zone_overlaps,
)
from tests.review_repo_helpers import git
from tests.test_orchestrate_plan import plan_repo


def _leaf(n: int, zones: list[str]) -> dict:
    return {
        "id": f"M1.{n}", "node_key": f"1{n}000000-0000-4000-8000-00000000000{n}",
        "type": "task", "title": f"M1.{n}", "status": "Not Started",
        "codename": f"cn-{n}", "dependencies": [], "parent_id": None,
        "sibling_order": n, "touch_zones": zones,
    }


def _plan(*zones: list[str]):
    nodes = [_leaf(i + 1, z) for i, z in enumerate(zones)]
    return compute_session_plan(nodes, {"version": 1, "entries": []})


def test_shared_file_path_moves_later_leaf_to_next_batch() -> None:
    plan = _plan(["src/a.py"], ["src/b.py"], ["./src/a.py", "docs/x.md"])
    assert plan.parallel_batches == [["M1.1", "M1.2"], ["M1.3"]]
    assert plan.ready == ["M1.1", "M1.2", "M1.3"]  # pickup order is untouched
    held = [{"node_id": "M1.3", "waits_for": "M1.1", "zones": ["./src/a.py", "src/a.py"]}]
    assert zone_overlaps(plan) == held
    assert session_plan_to_dict(plan)["zone_overlaps"] == held
    assert "touch_zones" not in session_plan_to_dict(plan)["waves"][0]
    text = render_session_plan_text(plan)
    assert "**Dispatch now (parallel, in pickup order):** M1.1, M1.2 " in text
    assert "- `M1.3` waits for `M1.1`: `./src/a.py` overlaps `src/a.py`" in text


def test_shared_directory_prefix_moves_later_leaf_either_way_round() -> None:
    plan = _plan(["src/pkg/mod.py"], ["src/pkg/"], ["src"])
    assert plan.parallel_batches == [["M1.1"], ["M1.2"], ["M1.3"]]
    assert [(h["node_id"], h["waits_for"]) for h in zone_overlaps(plan)] == [
        ("M1.2", "M1.1"), ("M1.3", "M1.2"),
    ]


def test_sibling_name_sharing_a_prefix_string_is_not_an_overlap() -> None:
    plan = _plan(["src/pkg"], ["src/pkg2/x.py"], ["src/pkg.py"], [])
    assert plan.parallel_batches == [["M1.1", "M1.2", "M1.3", "M1.4"]]
    assert zone_overlaps(plan) == []
    assert "waits for" not in render_session_plan_text(plan)


def test_git_rebuild_releases_a_leaf_whose_overlap_left_the_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`--plan` rebuilds the batches after dropping leaves finished on a branch."""
    plan = _plan(["src/a.py"], ["src/a.py"])
    assert plan.parallel_batches == [["M1.1"], ["M1.2"]]
    # Stub only the git lookup: M1.1 is Complete on its unmerged feature branch.
    monkeypatch.setattr(session_plan_git, "finished_unmerged_ids",
                        lambda cands, **_: ({c["id"] for c in cands if c["id"] == "M1.1"}, []))
    nodes = [_leaf(1, ["src/a.py"]), _leaf(2, ["src/a.py"])]
    plan = session_plan_git.enrich_session_plan_with_git(
        plan, nodes, repo_root=tmp_path, remote="origin", integration_branch="dev")
    assert plan.parallel_batches == [["M1.2"]]
    assert zone_overlaps(plan) == []


def test_orchestrate_plan_applies_the_same_split(tmp_path: Path) -> None:
    repo = plan_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    data = json.loads(chunk.read_text())
    data["nodes"].append({**_leaf(2, ["src/a.py"]), "codename": "other"})
    chunk.write_text(json.dumps(data))
    git(repo, "commit", "-qam", "second leaf in src/")
    plan, err = op.build_orchestration_plan(repo, today=date(2026, 11, 1))
    assert err is None and plan is not None
    assert [[a.node_id for a in b] for b in plan.batches] == [["M1.1"], ["M1.2"]]
