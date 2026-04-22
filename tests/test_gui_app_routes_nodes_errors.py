"""Error-handling regressions for ``specy_road.gui_app_routes_nodes``.

These tests pin down the **graceful 4xx** contract for failure modes that
previously surfaced as bare FastAPI 5xx (or as inconsistent status codes).
They complement the unit-level coverage in ``tests/test_milestone_lock.py``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD


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


def test_pm_milestone_lock_guard_returns_409_when_roadmap_unreadable(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transiently-broken roadmap must surface as **409**, not as a bare 500.

    The GUI's transparent retry only fires on 4xx contention; a 500 stops the
    retry loop and confuses the user. ``_pm_milestone_lock_guard`` calls
    ``load_roadmap`` and must absorb its failure modes (corrupt chunk,
    missing manifest, OS errors) into 409 with a human-readable hint.
    """
    headers = _mutation_headers(api_client)

    # Build the request first (fingerprint already captured), then break the
    # roadmap loader so the lock guard fails as soon as the route runs.
    from specy_road import gui_app_routes_nodes as routes

    def _boom(_root: Path) -> dict:
        raise OSError("simulated unreadable roadmap chunk")

    monkeypatch.setattr(routes, "load_roadmap", _boom)

    r = api_client.patch(
        "/api/nodes/M0.1",
        headers={**headers, "Content-Type": "application/json"},
        json={"pairs": [{"key": "status", "value": "Not Started"}]},
    )
    assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "")
    assert "milestone lock" in detail
    assert "specy-road validate" in detail


def test_pm_milestone_lock_guard_returns_409_for_value_error_in_roadmap_load(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ValueError`` from the loader (bad JSON / schema mismatch) is also 409."""
    headers = _mutation_headers(api_client)
    from specy_road import gui_app_routes_nodes as routes

    def _boom(_root: Path) -> dict:
        raise ValueError("manifest references missing chunk 'phases/X.json'")

    monkeypatch.setattr(routes, "load_roadmap", _boom)

    r = api_client.delete("/api/nodes/M0.1", headers=headers)
    assert r.status_code == 409
    assert "milestone lock" in r.json().get("detail", "")


def test_outline_move_unknown_node_key_is_400_not_404(
    api_client: TestClient,
) -> None:
    """Documented contract: unknown ``node_key`` → 400 with ``unknown node_key …``.

    Regression net for the lock-guard pre-lookup that briefly returned 404.
    """
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
    detail = r.json().get("detail", "")
    assert "node_key" in detail


def test_pm_gui_fingerprint_returns_409_when_manifest_unreadable(
    api_client: TestClient,
    dogfood_copy: Path,
) -> None:
    """Corrupt manifest must surface as **409**, not 500.

    Reproduces a real Phase 3 e2e finding: when the roadmap manifest is
    transiently broken (mid-edit save, conflict marker, partial write),
    ``outline_mutation_fingerprint`` raises ``json.JSONDecodeError``
    inside the FastAPI dependency. Without a guard, this leaks as a
    bare 500 and stops the bundled UI's transparent retry loop. The
    fix wraps the fingerprint computation in
    ``require_pm_gui_mutation_fingerprint`` and returns 409 with a
    structured ``{message, error, retryable: false}`` body that points
    the user at ``specy-road validate``.
    """
    headers = _mutation_headers(api_client)
    manifest = dogfood_copy / "roadmap" / "manifest.json"
    saved = manifest.read_text(encoding="utf-8")
    try:
        manifest.write_text("@@@ broken json @@@\n", encoding="utf-8")
        r = api_client.patch(
            "/api/nodes/M1",
            headers={**headers, "Content-Type": "application/json"},
            json={"pairs": [{"key": "notes", "value": "x"}]},
        )
    finally:
        manifest.write_text(saved, encoding="utf-8")

    assert r.status_code == 409, (
        f"expected 409, got {r.status_code}: {r.text}"
    )
    detail = r.json().get("detail", {})
    if isinstance(detail, dict):
        assert "specy-road validate" in detail.get("message", "")
        assert "JSONDecodeError" in detail.get("error", "")
        assert detail.get("retryable") is False
    else:  # legacy string detail still acceptable, must mention validate
        assert "specy-road validate" in detail
