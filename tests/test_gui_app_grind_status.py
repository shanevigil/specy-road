"""M17.14: ``GET /api/grind-status`` serves M22.68's status object unchanged, read-only.

Temporary repos built with ``tests.test_grind_status``'s helpers; ``now`` is pinned through
``create_app(clock=...)`` so the route body can be compared with the builder's output byte for byte.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from starlette.testclient import TestClient

from specy_road.brainstorm_session import BrainstormSession, write_session
from specy_road.bundled_scripts import grind_session as gs
from specy_road.bundled_scripts.grind_session_args import parse_grind_session_args
from specy_road.grind_status import build_report
from specy_road.gui_app import create_app
from specy_road.milestone_session import milestone_session_path, write_milestone_session
from specy_road.session_presence import start_session
from specy_road.worker_state import create_record
from tests.test_grind_status import D1, D2, branch_with, claim, commit, git, make_repo, node, set_status

MOCK = Path(__file__).resolve().parents[1] / "gui" / "pm-gantt" / "src" / "fixtures" / "grind_status_mock.json"
# Every leaf the live clock can see: a presence session expires by the wall clock, so ``now`` is pinned near it.
NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One leaf in each bucket, an open ledger entry in and out of scope, sessions and an unreadable brainstorm."""
    nodes = [
        node("M1", typ="phase"), node("M1.1", parent="M1"), node("M1.2", parent="M1", deps=("M1.20",)),
        node("M1.3", parent="M1"), node("M1.4", parent="M1"), node("M1.5", parent="M1", deps=("M1.4",)),
        node("M1.6", parent="M1"), node("M1.7", parent="M1"), node("M1.20", parent="M1", typ="gate"),
        node("M2", typ="phase"), node("M2.1", parent="M2"),
    ]
    root = make_repo(tmp_path, nodes, entries=(claim("M1.3"),), unauthored=("M1.7",))
    branch_with(root, "m1-3", path="src/M1.3.py")
    branch_with(root, "m1-6", complete="M1.6")
    set_status(root, "M1.1", "Complete")
    (root / "roadmap" / "decisions.yaml").write_text(
        yaml.safe_dump({"version": 1, "entries": [{**D1, "node": "M1.4"}, D2]}))
    commit(root, "finish M1.1, ledger")
    create_record(root, "M1.3", "claude-code", "opus", root)
    write_session(root, BrainstormSession(slug="open-one", mode="roadmap"))
    (root / "work" / "brainstorm-broken.yaml").write_bytes(b"version: [\n")
    start_session(root, "planner-a", paths=[], note="planner: status")
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(root))
    return root


def client(**kw) -> TestClient:
    return TestClient(create_app(clock=lambda: NOW, **kw))


def key_paths(v, prefix: str = "") -> set[str]:
    """``a.b`` for object keys, ``a[]`` for any list item, the union over items."""
    out: set[str] = {prefix} if prefix else set()
    if isinstance(v, dict):
        for k, x in v.items():
            out |= key_paths(x, f"{prefix}.{k}" if prefix else k)
    elif isinstance(v, list):
        for x in v:
            out |= key_paths(x, f"{prefix}[]")
    return out


def test_route_body_is_the_builders_object_byte_for_byte(repo: Path) -> None:
    r = client().get("/api/grind-status", params={"until": "M1"})
    assert r.status_code == 200
    report = build_report(repo, "M1", None, NOW)
    assert r.content == json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode()
    assert report["generated_at"] == NOW.isoformat()


def test_no_parameters_is_the_milestone_session_parent(repo: Path) -> None:
    write_milestone_session(milestone_session_path(repo / "work"), parent_node_id="M1", parent_codename="m1",
                            integration_branch="dev", remote="origin")
    c = client()
    default, under = c.get("/api/grind-status").json(), c.get("/api/grind-status?under=M1").json()
    assert ".milestone-session.yaml" in default["scope"].pop("rule")
    under["scope"].pop("rule")
    assert default == under


@pytest.mark.parametrize("params", [{}, {"until": "M99"}])
def test_the_clis_exit_2_cases_answer_400_with_its_message(repo: Path, capsys, params: dict) -> None:
    r = client().get("/api/grind-status", params=params)
    argv = [x for k, v in params.items() for x in (f"--{k}", v)]
    capsys.readouterr()
    assert gs.run_session(parse_grind_session_args(["--status", *argv, "--repo-root", str(repo)])) == 2
    assert r.status_code == 400
    assert capsys.readouterr().err == f"error: {r.json()['detail']}\n"


def test_read_only_serves_the_get_refuses_a_post_and_changes_nothing(repo: Path) -> None:
    def state() -> tuple:
        return (git(repo, "status", "--porcelain"), git(repo, "rev-parse", "HEAD"),
                (repo / "roadmap" / "registry.yaml").read_bytes(), (repo / "roadmap" / "decisions.yaml").read_bytes())

    before = state()
    c = client(read_only=True)
    assert c.get("/api/grind-status", params={"under": "M1"}).status_code == 200
    post = c.post("/api/grind-status", params={"under": "M1"})
    assert post.status_code == 403 and "read-only" in post.json()["detail"]
    assert state() == before


def test_the_gui_mock_has_the_routes_key_paths_both_ways(repo: Path) -> None:
    body = client().get("/api/grind-status", params={"until": "M1"}).json()
    mock = json.loads(MOCK.read_text())
    assert key_paths(body) - key_paths(mock) == set(), "the route sends fields the mock lacks"
    assert key_paths(mock) - key_paths(body) == set(), "the mock has fields the route never sends"
    del body["estimate"]["reason"]   # a dropped field fails the comparison
    assert key_paths(body) != key_paths(mock)
