"""PM Gantt API: planning writes, node CRUD, outline errors."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD

_M02_PLANNING = (
    "planning/M0.2_roadmap-ci_e7fcdb23-5d23-5bbf-a9b5-aaa0140ff208.md"
)


def _mutation_headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/roadmap")
    assert r.status_code == 200
    return {"X-PM-Gui-Fingerprint": str(r.json()["fingerprint"])}


@pytest.fixture()
def dogfood_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dest)
    return dest


@pytest.fixture()
def api_client(
    dogfood_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))
    from specy_road.gui_app import create_app

    return TestClient(create_app())


def test_api_planning_put_success_updates_file(
    api_client: TestClient,
    dogfood_copy: Path,
) -> None:
    path = _M02_PLANNING
    sheet = dogfood_copy / path
    before = sheet.read_text(encoding="utf-8")
    updated = before + "\n"
    r = api_client.put(
        "/api/planning/file",
        params={"path": path},
        headers={**_mutation_headers(api_client), "Content-Type": "application/json"},
        json={"content": updated},
    )
    assert r.status_code == 200
    assert sheet.read_text(encoding="utf-8") == updated


def test_api_planning_put_orphan_file_unlinked_on_validation_failure(
    api_client: TestClient,
    dogfood_copy: Path,
) -> None:
    """Orphan planning file fails validation; rollback must unlink the new file."""
    rel = "planning/pytest_gui_orphan_only.md"
    target = dogfood_copy / rel
    assert not target.exists()
    r = api_client.put(
        "/api/planning/file",
        params={"path": rel},
        headers={**_mutation_headers(api_client), "Content-Type": "application/json"},
        json={"content": "# orphan\n"},
    )
    assert r.status_code == 400
    assert not target.exists()


def test_api_planning_put_restores_content_when_validate_fails(
    dogfood_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _M02_PLANNING
    sheet = dogfood_copy / path
    before = sheet.read_text(encoding="utf-8")
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))

    def _fail(_root: Path) -> None:
        raise ValueError("forced validation failure for test")

    monkeypatch.setattr(
        "specy_road.gui_app_routes_planning.run_validate_raise",
        _fail,
    )
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r = client.put(
        "/api/planning/file",
        params={"path": path},
        headers={**_mutation_headers(client), "Content-Type": "application/json"},
        json={"content": before + "\n# pytest touch\n"},
    )
    assert r.status_code == 400
    assert sheet.read_text(encoding="utf-8") == before


def test_api_patch_node_title_roundtrip(api_client: TestClient) -> None:
    r0 = api_client.get("/api/roadmap")
    assert r0.status_code == 200
    node = next(n for n in r0.json()["nodes"] if n["id"] == "M0.2")
    orig = node["title"]
    r1 = api_client.patch(
        "/api/nodes/M0.2",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json={"pairs": [{"key": "title", "value": f"{orig} [pytest]"}]},
    )
    assert r1.status_code == 200
    r2 = api_client.patch(
        "/api/nodes/M0.2",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json={"pairs": [{"key": "title", "value": orig}]},
    )
    assert r2.status_code == 200


def test_api_patch_node_rejects_disallowed_key(api_client: TestClient) -> None:
    r = api_client.patch(
        "/api/nodes/M0.2",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json={"pairs": [{"key": "not_whitelisted", "value": "x"}]},
    )
    assert r.status_code == 400


def test_api_outline_reorder_rejects_incomplete_child_set(
    api_client: TestClient,
) -> None:
    r = api_client.post(
        "/api/outline/reorder",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json={"parent_id": "M0", "ordered_child_ids": ["M0.1"]},
    )
    assert r.status_code == 400


def test_api_outline_move_rejects_unknown_node_key(
    api_client: TestClient,
) -> None:
    r = api_client.post(
        "/api/outline/move",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json={
            "node_key": "00000000-0000-0000-0000-000000000001",
            "new_parent_id": None,
            "new_index": 0,
        },
    )
    assert r.status_code == 400


def test_api_post_nodes_add_task(api_client: TestClient) -> None:
    r = api_client.post(
        "/api/nodes/add",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json={
            "reference_node_id": "M0.1",
            "position": "below",
            "title": "pytest GUI add-node",
            "type": "task",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") == "true"
    assert "id" in body


def test_api_post_nodes_add_auto_routes_when_reference_chunk_full(
    dogfood_copy: Path, api_client: TestClient
) -> None:
    """F-AUTO: GUI add-node falls back to a new chunk when the reference chunk is full."""
    # Tighten the cap below the current size of M0.json so any append would
    # overflow it; the router must auto-create a new chunk.
    chunk = dogfood_copy / "roadmap" / "phases" / "M0.json"
    cur_lines = sum(1 for _ in chunk.read_text(encoding="utf-8").splitlines())
    (dogfood_copy / "constraints" / "file-limits.yaml").write_text(
        f"roadmap_json_chunk_max_lines: {cur_lines + 5}\n", encoding="utf-8"
    )
    r = api_client.post(
        "/api/nodes/add",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json={
            "reference_node_id": "M0.1",
            "position": "below",
            "title": "GUI overflow",
            "type": "task",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    new_id = body["id"]
    # The new node lives outside M0.json (auto-routed).
    from roadmap_chunk_utils import find_chunk_path

    chunk_path = find_chunk_path(dogfood_copy, new_id)
    assert chunk_path is not None
    assert chunk_path.name != "M0.json"


def test_api_delete_leaf_node(api_client: TestClient) -> None:
    r = api_client.delete(
        "/api/nodes/M2",
        headers=_mutation_headers(api_client),
    )
    assert r.status_code == 200
    assert r.json().get("node_id") == "M2"
