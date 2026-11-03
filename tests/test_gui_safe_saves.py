"""Stale-save refusal, ``--read-only`` and the JSON ``/api`` 404 (M11.51)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD

PLANNING = "vision.md"
SHARED = "shared/README.md"
ROUTES = [("/api/planning/file", PLANNING), ("/api/workspace/file", SHARED)]


@pytest.fixture()
def dogfood_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dest = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dest)
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dest))
    return dest


def _client(read_only: bool = False) -> TestClient:
    from specy_road.gui_app import create_app

    return TestClient(create_app(read_only=read_only))


def _headers(client: TestClient, base_hash: str | None = None) -> dict[str, str]:
    r = client.get("/api/roadmap")
    assert r.status_code == 200
    h = {"X-PM-Gui-Fingerprint": str(r.json()["fingerprint"])}
    if base_hash is not None:
        h["X-Base-Content-Hash"] = base_hash
    return h


@pytest.mark.parametrize(("route", "rel"), ROUTES)
def test_stale_save_refused_with_current_content(
    dogfood_copy: Path, route: str, rel: str,
) -> None:
    client = _client()
    got = client.get(route, params={"path": rel}).json()
    assert len(got["content_hash"]) == 64
    (dogfood_copy / rel).write_text("edited on disk\n", encoding="utf-8")
    r = client.put(
        route,
        params={"path": rel},
        json={"content": "stale dashboard save\n"},
        headers=_headers(client, got["content_hash"]),
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["current_content"] == "edited on disk\n"
    assert detail["content_hash"] != got["content_hash"]
    assert (dogfood_copy / rel).read_text(encoding="utf-8") == "edited on disk\n"


@pytest.mark.parametrize(("route", "rel"), ROUTES)
def test_fresh_save_accepted_and_returns_new_hash(
    dogfood_copy: Path, route: str, rel: str,
) -> None:
    client = _client()
    got = client.get(route, params={"path": rel}).json()
    new = got["content"] + "\nappended by the dashboard\n"
    r = client.put(
        route,
        params={"path": rel},
        json={"content": new},
        headers=_headers(client, got["content_hash"]),
    )
    assert r.status_code == 200, r.text
    assert (dogfood_copy / rel).read_text(encoding="utf-8") == new
    again = client.get(route, params={"path": rel}).json()
    assert r.json()["content_hash"] == again["content_hash"] != got["content_hash"]


def test_read_only_serves_reads_and_refuses_writes(dogfood_copy: Path) -> None:
    client = _client(read_only=True)
    assert client.get("/api/roadmap").status_code == 200
    before = (dogfood_copy / SHARED).read_text(encoding="utf-8")
    r = client.put(
        "/api/workspace/file",
        params={"path": SHARED},
        json={"content": "nope\n"},
        headers=_headers(client),
    )
    assert r.status_code == 403
    assert "read-only" in r.json()["detail"]
    assert (dogfood_copy / SHARED).read_text(encoding="utf-8") == before


def test_read_only_from_env(
    dogfood_copy: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_GUI_READ_ONLY", "1")
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    assert client.post("/api/constitution/scaffold", json={}).status_code == 403


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_unknown_api_path_is_json_404(dogfood_copy: Path, method: str) -> None:
    r = _client().request(method, "/api/no-such-route/here")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert "no-such-route" in r.json()["detail"]
