"""PM Gantt archive API: reads, writes, and the concurrency guard.

An archive moves roadmap files, so the write routes must be as protected as any
other mutation — a stale browser tab firing one against a graph it has not seen
is exactly what the fingerprint header exists to stop.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest


@pytest.fixture()
def client(repo: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(repo))
    from specy_road.gui_app import create_app

    return TestClient(create_app())


def _headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/roadmap")
    assert r.status_code == 200
    return {"X-PM-Gui-Fingerprint": str(r.json()["fingerprint"])}


def test_listing_is_empty_before_anything_is_archived(client: TestClient) -> None:
    body = client.get("/api/archives").json()
    assert body["records"] == []
    assert [e["node_id"] for e in body["eligible"]] == ["M0.1", "M0.3"]


def test_eligibility_matches_what_the_cli_would_allow(client: TestClient) -> None:
    """The button must not appear on something `plan_archive` would refuse."""
    eligible = {e["node_id"] for e in client.get("/api/archives").json()["eligible"]}
    assert "M0.2" not in eligible  # Not Started
    assert "M0" not in eligible  # rolls up Not Started


def test_preview_writes_nothing(client: TestClient, repo: Path) -> None:
    r = client.post("/api/archives/preview", json={"node_id": "M0.1"})
    assert r.status_code == 200
    assert any("M0.1" in line for line in r.json()["summary"])
    assert not (repo / "roadmap" / "archive").exists()


def test_preview_reports_an_ineligible_node(client: TestClient) -> None:
    r = client.post("/api/archives/preview", json={"node_id": "M0.2"})
    assert r.status_code == 400
    assert "not 'Complete'" in r.json()["detail"]


def test_create_then_list_then_restore(client: TestClient) -> None:
    created = client.post(
        "/api/archives/create", json={"node_id": "M0.1"}, headers=_headers(client)
    )
    assert created.status_code == 200, created.text
    archive_id = created.json()["archive_id"]

    listed = client.get("/api/archives").json()
    assert [r["archive_id"] for r in listed["records"]] == [archive_id]

    restored = client.post(
        f"/api/archives/{archive_id}/restore", headers=_headers(client)
    )
    assert restored.status_code == 200, restored.text
    assert client.get("/api/archives").json()["records"] == []


def test_create_requires_the_fingerprint_header(client: TestClient) -> None:
    r = client.post("/api/archives/create", json={"node_id": "M0.1"})
    assert r.status_code == 428


def test_a_stale_fingerprint_is_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/archives/create",
        json={"node_id": "M0.1"},
        headers={"X-PM-Gui-Fingerprint": "1"},
    )
    assert r.status_code == 412


def test_restore_requires_the_fingerprint_header(client: TestClient) -> None:
    created = client.post(
        "/api/archives/create", json={"node_id": "M0.1"}, headers=_headers(client)
    )
    archive_id = created.json()["archive_id"]

    assert client.post(f"/api/archives/{archive_id}/restore").status_code == 428


def test_browsing_a_shallow_archive_returns_its_nodes(client: TestClient) -> None:
    created = client.post(
        "/api/archives/create", json={"node_id": "M0.1"}, headers=_headers(client)
    )
    archive_id = created.json()["archive_id"]

    body = client.get(f"/api/archives/{archive_id}/nodes").json()
    assert body["browsable"] is True
    assert [n["id"] for n in body["nodes"]] == ["M0.1"]


def test_a_deep_archive_is_not_browsable(client: TestClient) -> None:
    """Rendering a page must not unpack a bundle."""
    created = client.post(
        "/api/archives/create",
        json={"node_id": "M0.1", "deep": True},
        headers=_headers(client),
    )
    archive_id = created.json()["archive_id"]

    body = client.get(f"/api/archives/{archive_id}/nodes").json()
    assert body["browsable"] is False
    assert body["depth"] == "deep"
    assert [n["id"] for n in body["nodes"]] == ["M0.1"]


def test_deep_create_produces_a_bundle_and_ref(client: TestClient, repo: Path) -> None:
    created = client.post(
        "/api/archives/create",
        json={"node_id": "M0.1", "deep": True},
        headers=_headers(client),
    ).json()

    assert created["depth"] == "deep"
    assert (repo / created["bundle"]["path"]).is_file()
    assert (repo / "roadmap/archive/refs" / f"{created['archive_id']}.json").is_file()


def test_unknown_archive_is_404(client: TestClient) -> None:
    assert client.get("/api/archives/nope-00000000-20260101").status_code == 404


def test_auto_dry_run_reports_without_writing(client: TestClient, repo: Path) -> None:
    r = client.post(
        "/api/archives/auto",
        json={"older_than_days": 0, "dry_run": True},
        headers=_headers(client),
    )
    assert r.status_code == 200
    assert r.json()["dry_run"] is True
    assert not (repo / "roadmap" / "archive").exists()


def test_the_roadmap_payload_carries_activity(client: TestClient) -> None:
    assert client.get("/api/roadmap").json()["activity"] == {}


def test_settings_expose_the_new_pm_gui_preferences(client: TestClient) -> None:
    pm = client.get("/api/settings").json()["pm_gui"]
    assert pm["auto_hide_completed"] is False
    assert pm["auto_archive_completed"] is False
    assert pm["auto_archive_after_days"] == 90


def test_auto_suggestions_are_absent_until_the_preference_is_on(
    client: TestClient,
) -> None:
    """The preference must actually gate something, or it is a dead control."""
    body = client.get("/api/archives").json()
    assert body["auto"]["enabled"] is False
    assert body["auto"]["candidates"] == []


def test_auto_suggestions_appear_when_the_preference_is_on(
    client: TestClient, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "specy_road.gui_app_routes_archive._auto_settings", lambda root: (True, 0)
    )
    body = client.get("/api/archives").json()

    assert body["auto"]["enabled"] is True
    assert {c["node_id"] for c in body["auto"]["candidates"]} <= {"M0.1", "M0.3"}


def test_listing_survives_a_failing_candidate_scan(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Suggestions are a convenience; they must not take down the archive list."""
    import specy_road.gui_app_routes_archive as mod

    monkeypatch.setattr(mod, "_auto_settings", lambda root: (True, 0))

    def boom(root, **kwargs):
        raise RuntimeError("scan exploded")

    monkeypatch.setattr(mod, "auto_archive_candidates", boom)

    r = client.get("/api/archives")
    assert r.status_code == 200
    assert r.json()["auto"]["candidates"] == []
    assert r.json()["records"] == []
