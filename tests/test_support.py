"""The shared test primitives in tests/support behave as the tests that use them assume."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from tests.helpers import DOGFOOD, SCHEMAS
from tests.review_repo_helpers import git
from tests.support.cli import run_cli, run_cli_subprocess
from tests.support.harness import make_worker_repo, run_fake_harness_turn
from tests.support.roadmap import node_key, roadmap_repo

from specy_road.orchestration.workers import worker_state as ws


def test_roadmap_repo_writes_a_graph_that_validates(tmp_path: Path) -> None:
    shutil.copytree(SCHEMAS, tmp_path / "schemas")
    phase = {"id": "M1", "type": "phase", "title": "Phase", "parent_id": None,
             "status": "Not Started"}
    leaf = {"id": "M1.1", "type": "task", "title": "Leaf", "codename": "leaf", "parent_id": "M1",
            "status": "Not Started", "dependencies": [], "touch_zones": ["src"]}
    entry = {"codename": "leaf", "node_id": "M1.1", "branch": "feature/rm-leaf",
             "touch_zones": ["src"]}
    workflow = "version: 1\nintegration_branch: dev\nremote: origin\n"
    roadmap_repo(tmp_path, [phase, leaf], registry=[entry], git_workflow=workflow)

    nodes = json.loads((tmp_path / "roadmap" / "phases" / "M1.json").read_text())["nodes"]
    assert [n["node_key"] for n in nodes] == [node_key("M1"), node_key("M1.1")]
    assert node_key("M1.1") == node_key("M1.1") != node_key("M1.2")
    assert (tmp_path / f"planning/M1.1_leaf_{node_key('M1.1')}.md").read_text() == "# M1.1\n"
    registry = yaml.safe_load((tmp_path / "roadmap" / "registry.yaml").read_text())
    assert registry["entries"] == [entry]
    assert (tmp_path / "roadmap" / "git-workflow.yaml").read_text() == workflow
    result = run_cli(["validate", "--repo-root", str(tmp_path)])
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_git_remote_repo_copy_leaves_the_template_unchanged(
    git_template: tuple[Path, Path], git_remote_repo: tuple[Path, Path]
) -> None:
    template_repo, template_bare = git_template
    repo, bare = git_remote_repo
    before = git(template_repo, "rev-parse", "HEAD"), git(template_bare, "for-each-ref")
    assert git(repo, "rev-parse", "HEAD") == before[0]

    (repo / "change.txt").write_text("x\n", encoding="utf-8")
    git(repo, "add", "change.txt")
    git(repo, "commit", "-qm", "change")
    git(repo, "push", "-q", "origin", "dev")

    assert git(bare, "rev-parse", "dev") == git(repo, "rev-parse", "HEAD") != before[0]
    assert (git(template_repo, "rev-parse", "HEAD"), git(template_bare, "for-each-ref")) == before


@pytest.mark.parametrize(("argv", "code"), [(["--version"], 0), (["no-such-command"], 2)])
def test_run_cli_and_run_cli_subprocess_agree(argv: list[str], code: int) -> None:
    here, child = run_cli(argv), run_cli_subprocess(argv)
    assert (here.returncode, here.stdout, here.stderr) == (
        child.returncode, child.stdout, child.stderr)
    assert here.returncode == code


def test_dogfood_copy_is_a_private_copy(dogfood_copy: Path) -> None:
    manifest = dogfood_copy / "roadmap" / "manifest.json"
    original = (DOGFOOD / "roadmap" / "manifest.json").read_text(encoding="utf-8")
    assert manifest.read_text(encoding="utf-8") == original
    manifest.write_text("{}\n", encoding="utf-8")
    assert (DOGFOOD / "roadmap" / "manifest.json").read_text(encoding="utf-8") == original


def test_api_client_serves_the_dogfood_copy(api_client, dogfood_copy: Path) -> None:
    response = api_client.get("/api/roadmap")
    assert response.status_code == 200
    ids = {n["id"] for n in response.json()["nodes"]}
    chunk = json.loads(next((dogfood_copy / "roadmap" / "phases").glob("*.json")).read_text())
    assert {n["id"] for n in chunk["nodes"]} <= ids


def test_fake_harness_turn_records_the_session_and_its_completion(tmp_path: Path) -> None:
    repo, script = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "claude-code", "opus", repo)
    lines = [{"type": "system", "subtype": "init", "session_id": "s-fake", "model": "fake"},
             {"type": "result", "subtype": "success", "result": "done", "session_id": "s-fake"}]
    run_fake_harness_turn(repo, script, rec, lines)
    assert ws.load_record(repo, rec.worker_id).provider_session_id == "s-fake"
    assert [e.type for e in ws.events_since(repo, rec.worker_id)][-1] == "completion"
