"""End-to-end PM API tests for the milestone subtree lock guard.

These tests boot the FastAPI app against a copy of the dogfood roadmap,
attach an active ``milestone_execution`` to one milestone parent, and
verify that mutating routes return **409** for nodes inside the locked
subtree while still allowing edits elsewhere.

Complements ``tests/test_milestone_lock.py`` (unit-level coverage of
``milestone_lock.assert_pm_nodes_not_milestone_locked``).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD


def _mutation_headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/roadmap")
    assert r.status_code == 200
    return {"X-PM-Gui-Fingerprint": str(r.json()["fingerprint"])}


def _attach_active_lock_to(repo_root: Path, parent_id: str) -> None:
    chunks_dir = repo_root / "roadmap" / "phases"
    for chunk in chunks_dir.glob("*.json"):
        doc = json.loads(chunk.read_text(encoding="utf-8"))
        nodes = doc["nodes"] if isinstance(doc, dict) else doc
        changed = False
        for n in nodes:
            if isinstance(n, dict) and n.get("id") == parent_id:
                n["milestone_execution"] = {
                    "state": "active",
                    "rollup_branch": f"feature/rm-{n.get('codename') or 'tmp'}",
                    "integration_branch": "dev",
                    "remote": "origin",
                }
                changed = True
        if changed:
            chunk.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
            return
    raise AssertionError(f"could not find chunk for {parent_id!r}")


def _node_key_for(repo_root: Path, node_id: str) -> str:
    for chunk in (repo_root / "roadmap" / "phases").glob("*.json"):
        doc = json.loads(chunk.read_text(encoding="utf-8"))
        nodes = doc["nodes"] if isinstance(doc, dict) else doc
        for n in nodes:
            if isinstance(n, dict) and n.get("id") == node_id:
                return n["node_key"]
    raise AssertionError(f"unknown node id {node_id!r}")


@pytest.fixture()
def locked_dogfood(tmp_path: Path) -> Path:
    dest = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dest)
    # Lock the M0 subtree — its descendants (M0.1, M0.2, M0.3) become
    # read-only via the PM API while the milestone is active.
    _attach_active_lock_to(dest, "M0")
    return dest


@pytest.fixture()
def api_client_locked(
    locked_dogfood: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(locked_dogfood))
    from specy_road.gui_app import create_app

    return TestClient(create_app())


def test_patch_node_under_locked_milestone_returns_409(
    api_client_locked: TestClient,
) -> None:
    headers = _mutation_headers(api_client_locked)
    r = api_client_locked.patch(
        "/api/nodes/M0.1",
        headers={**headers, "Content-Type": "application/json"},
        json={"pairs": [{"key": "status", "value": "Not Started"}]},
    )
    assert r.status_code == 409, r.text
    detail = r.json().get("detail", "")
    assert "milestone subtree" in detail
    # Hint must point at the documented escape hatch.
    assert "reconcile-milestone-status" in detail


def test_patch_node_outside_locked_subtree_still_works(
    api_client_locked: TestClient,
) -> None:
    """M1 is not under the locked M0 subtree — edits must still go through."""
    headers = _mutation_headers(api_client_locked)
    r = api_client_locked.patch(
        "/api/nodes/M1",
        headers={**headers, "Content-Type": "application/json"},
        json={"pairs": [{"key": "status", "value": "Not Started"}]},
    )
    # 200 OK or 400 (legit validation rejection — e.g. status already that
    # value) are both acceptable: the lock did NOT block it.
    assert r.status_code in (200, 400), r.text
    if r.status_code == 400:
        assert "milestone subtree" not in r.json().get("detail", "")


def test_outline_move_into_locked_subtree_returns_409(
    api_client_locked: TestClient,
    locked_dogfood: Path,
) -> None:
    """Moving an unlocked node *into* the locked subtree is also blocked."""
    moved_key = _node_key_for(locked_dogfood, "M1")  # unlocked source
    headers = _mutation_headers(api_client_locked)
    r = api_client_locked.post(
        "/api/outline/move",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "node_key": moved_key,
            "new_parent_id": "M0",  # locked target
            "new_index": 0,
        },
    )
    assert r.status_code == 409, r.text
    assert "milestone subtree" in r.json().get("detail", "")


def test_indent_inside_locked_subtree_returns_409(
    api_client_locked: TestClient,
) -> None:
    headers = _mutation_headers(api_client_locked)
    r = api_client_locked.post(
        "/api/nodes/M0.1/indent",
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert "milestone subtree" in r.json().get("detail", "")


def test_delete_inside_locked_subtree_returns_409(
    api_client_locked: TestClient,
) -> None:
    headers = _mutation_headers(api_client_locked)
    r = api_client_locked.delete("/api/nodes/M0.3", headers=headers)
    assert r.status_code == 409, r.text
    assert "milestone subtree" in r.json().get("detail", "")
