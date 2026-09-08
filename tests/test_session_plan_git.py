"""Tests for git-aware session plan enrichment (plan/pickup parity)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from specy_road.bundled_scripts.session_plan import compute_session_plan
from specy_road.bundled_scripts.session_plan_git import enrich_session_plan_with_git
from specy_road.bundled_scripts.session_plan_render import render_session_plan_text


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )


def _write_graph(repo: Path, status: str, *, node_id: str = "M1.1", codename: str = "leaf-a") -> None:
    roadmap = repo / "roadmap"
    (roadmap / "phases").mkdir(parents=True, exist_ok=True)
    (roadmap / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/M1.json"]}), encoding="utf-8"
    )
    (roadmap / "phases" / "M1.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": node_id,
                        "node_key": "11111111-1111-5111-8111-111111111111",
                        "codename": codename,
                        "title": node_id,
                        "type": "task",
                        "parent_id": None,
                        "sibling_order": 1,
                        "status": status,
                        "dependencies": [],
                        "touch_zones": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q", "-b", "dev")
    _git(root, "config", "user.email", "t@e.com")
    _git(root, "config", "user.name", "T")
    _write_graph(root, "Not Started")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "graph")
    return root


def _node(codename: str, node_id: str = "M1.1") -> dict:
    return {
        "id": node_id,
        "node_key": "11111111-1111-5111-8111-111111111111",
        "codename": codename,
        "type": "task",
        "title": node_id,
        "status": "Not Started",
        "dependencies": [],
    }


def test_enrich_drops_finished_unmerged_from_ready(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feature/rm-leaf-a")
    _write_graph(repo, "Complete")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "done")
    _git(repo, "checkout", "-q", "dev")

    nodes = [_node("leaf-a")]
    plan = compute_session_plan(nodes, {"version": 1, "entries": []})
    assert plan.ready == ["M1.1"]

    enriched = enrich_session_plan_with_git(
        plan, nodes, repo_root=repo, remote="origin", integration_branch="dev"
    )
    assert enriched.ready == []
    assert enriched.finished_unmerged == ["M1.1"]
    assert enriched.parallel_batches == []


def test_enrich_surfaces_finished_claimed_on_active(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feature/rm-leaf-a")
    _write_graph(repo, "Complete")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "done")
    _git(repo, "checkout", "-q", "dev")

    nodes = [_node("leaf-a")]
    reg = {
        "version": 1,
        "entries": [
            {
                "codename": "leaf-a",
                "node_id": "M1.1",
                "branch": "feature/rm-leaf-a",
            }
        ],
    }
    plan = compute_session_plan(nodes, reg)
    assert "M1.1" in plan.active
    assert "M1.1" not in plan.ready

    enriched = enrich_session_plan_with_git(
        plan, nodes, repo_root=repo, remote="origin", integration_branch="dev"
    )
    assert enriched.finished_claimed == ["M1.1"]
    assert enriched.finished_unmerged == []


def test_render_shows_finished_on_branch_sections(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feature/rm-leaf-a")
    _write_graph(repo, "Complete")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "done")
    _git(repo, "checkout", "-q", "dev")

    nodes = [
        _node("leaf-a", "M1.1"),
        {
            "id": "M1.2",
            "node_key": "22222222-2222-5222-8222-222222222222",
            "codename": "leaf-b",
            "type": "task",
            "title": "M1.2",
            "status": "Not Started",
            "dependencies": [],
        },
    ]
    plan = compute_session_plan(nodes, {"version": 1, "entries": []})
    enriched = enrich_session_plan_with_git(
        plan, nodes, repo_root=repo, remote="origin", integration_branch="dev"
    )
    text = render_session_plan_text(enriched)
    assert "Finished on branch (pickup skips)" in text
    assert "M1.1" in text
    assert "Unclaimed" in text
    assert "Next auto-pick" in text and "`M1.2`" in text


def test_render_finished_claimed_says_merge_not_finish(repo: Path) -> None:
    _git(repo, "checkout", "-q", "-b", "feature/rm-leaf-a")
    _write_graph(repo, "Complete")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "done")
    _git(repo, "checkout", "-q", "dev")

    nodes = [_node("leaf-a")]
    reg = {
        "version": 1,
        "entries": [
            {
                "codename": "leaf-a",
                "node_id": "M1.1",
                "branch": "feature/rm-leaf-a",
            }
        ],
    }
    plan = compute_session_plan(nodes, reg)
    enriched = enrich_session_plan_with_git(
        plan, nodes, repo_root=repo, remote="origin", integration_branch="dev"
    )
    text = render_session_plan_text(enriched)
    assert "Still claimed, Complete on branch" in text
    assert "open or merge the PR" in text
    assert "Do not re-run" in text
