"""`sensitivity` and `executor_eligibility` as node fields (slices note, decisions A and B)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road.bundled_scripts.roadmap_crud import main as crud_main
from specy_road.bundled_scripts.roadmap_edit_fields import apply_set
from specy_road.bundled_scripts.validate_roadmap import validate_at
from specy_road.orchestrate_plan import node_eligibility, node_sensitivity


def _node(repo: Path, nid: str = "M1.1") -> dict:
    chunk = json.loads((repo / "roadmap" / "phases" / "M1.json").read_text())
    return next(n for n in chunk["nodes"] if n["id"] == nid)


def _crud(repo: Path, *args: str) -> None:
    try:
        crud_main(["--repo-root", str(repo), *args])
    except SystemExit as e:
        assert (e.code or 0) == 0


def test_validate_accepts_the_fields(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    chunk = repo / "roadmap" / "phases" / "M1.json"
    chunk.write_text(chunk.read_text().replace('"id": "M1.1",', '"id": "M1.1", "sensitivity": "restricted", "executor_eligibility": "senior",'))
    validate_at(repo)  # raises SystemExit(1) on a schema rejection
    n = _node(repo)
    assert node_sensitivity(n) == "restricted" and node_eligibility(n) == "senior"


def test_edit_node_sets_and_clears_them(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _crud(repo, "edit-node", "M1.1", "--set", "sensitivity=internal", "--set", "executor_eligibility=senior")
    n = _node(repo)
    assert n["sensitivity"] == "internal" and n["executor_eligibility"] == "senior"
    _crud(repo, "edit-node", "M1.1", "--set", "sensitivity=", "--set", "executor_eligibility=")
    n = _node(repo)
    assert "sensitivity" not in n and "executor_eligibility" not in n
    assert node_sensitivity(n) == "public" and node_eligibility(n) == "any"


def test_a_bad_tag_is_refused() -> None:
    with pytest.raises(ValueError, match="single tag"):
        apply_set({"id": "x"}, "sensitivity", "restricted, personal", all_ids=set(), all_node_keys=set(), self_id="x")


def test_add_node_flags_write_them(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    _crud(repo, "add-node", "--id", "M1.2", "--type", "task", "--title", "Second", "--parent-id", "null",
          "--sensitivity", "restricted", "--executor-eligibility", "senior")
    n = _node(repo, "M1.2")
    assert n["sensitivity"] == "restricted" and n["executor_eligibility"] == "senior"
    validate_at(repo)
