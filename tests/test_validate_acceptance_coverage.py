"""`validate` warns on leaves a review cannot attest per criterion while the gate is on.

`acceptance_ids` is `[]` for a leaf without `acceptance`, so `acceptance: {}` is
a complete review record for it. With the review gate on that is a review that
attests nothing criterion by criterion; this warning names such leaves.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.review_repo_helpers import make_review_repo

from specy_road.bundled_scripts.brief_acceptance import warn_acceptance_missing
from specy_road.bundled_scripts.validate_roadmap import validate_at


def _node(nid: str = "M1.1", **over) -> dict:
    base = {"id": nid, "type": "task", "status": "Not Started", "acceptance": []}
    base.update(over)
    return base


def _warn(nodes: list[dict], gate_on: bool, capsys) -> str:
    capsys.readouterr()
    warn_acceptance_missing(nodes, gate_on)
    return capsys.readouterr().err


def test_gate_on_and_a_bare_leaf_warns(capsys) -> None:
    err = _warn([_node()], True, capsys)
    assert "warning: M1.1 has no acceptance criteria" in err
    assert "specy-road edit-node M1.1 --set acceptance=" in err


def test_gate_off_is_silent(capsys) -> None:
    assert _warn([_node()], False, capsys) == ""


def test_complete_leaf_gate_node_and_parent_are_silent(capsys) -> None:
    nodes = [
        _node("M1", type="milestone"),
        _node("M1.1", parent_id="M1", status="Complete"),
        _node("M1.2", parent_id="M1", type="gate"),
        _node("M1.3", parent_id="M1", acceptance=["it works"]),
    ]
    assert _warn(nodes, True, capsys) == ""


def test_the_warning_is_capped(capsys) -> None:
    err = _warn([_node(f"M1.{i}") for i in range(1, 14)], True, capsys)
    assert err.count("has no acceptance criteria") == 10
    assert "… and 3 more leaves without acceptance criteria" in err


def test_validate_prints_one_warning_and_passes(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    data = json.loads(chunk.read_text())
    del data["nodes"][0]["acceptance"]
    chunk.write_text(json.dumps(data))
    capsys.readouterr()
    validate_at(repo, no_overlap_warn=True, require_registry=True)
    out = capsys.readouterr()
    assert out.err.count("has no acceptance criteria") == 1
    assert "OK: roadmap and registry validate." in out.out
