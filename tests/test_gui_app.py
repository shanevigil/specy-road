from __future__ import annotations

import base64
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD


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


def test_api_repo_follows_cwd_when_env_unset(
    dogfood_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without SPECY_ROAD_REPO_ROOT, repo root follows cwd like other CLI."""
    monkeypatch.delenv("SPECY_ROAD_REPO_ROOT", raising=False)
    monkeypatch.chdir(dogfood_copy)
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r = client.get("/api/repo")
    assert r.status_code == 200
    assert Path(r.json()["repo_root"]).resolve() == dogfood_copy.resolve()
    r2 = client.get("/api/roadmap")
    assert r2.status_code == 200
    assert "nodes" in r2.json()


def test_api_repo_env_overrides_cwd(
    dogfood_copy: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECY_ROAD_REPO_ROOT wins over cwd (e.g. ``gui --repo-root playground``)."""
    elsewhere = tmp_path / "not_the_playground"
    elsewhere.mkdir()
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))
    monkeypatch.chdir(elsewhere)
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r = client.get("/api/repo")
    assert r.status_code == 200
    assert Path(r.json()["repo_root"]).resolve() == dogfood_copy.resolve()
    r2 = client.get("/api/roadmap")
    assert r2.status_code == 200
    assert "nodes" in r2.json()


def test_api_health(api_client: TestClient) -> None:
    r = api_client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_api_roadmap_returns_nodes(api_client: TestClient) -> None:
    r = api_client.get("/api/roadmap")
    assert r.status_code == 200
    data = r.json()
    assert "nodes" in data
    assert isinstance(data["nodes"], list)
    assert len(data["nodes"]) >= 1


_M02_PLANNING = (
    "planning/M0.2_roadmap-ci_e7fcdb23-5d23-5bbf-a9b5-aaa0140ff208.md"
)


def test_api_planning_file_reads_existing(api_client: TestClient) -> None:
    r = api_client.get(
        "/api/planning/file",
        params={"path": _M02_PLANNING},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["path"].startswith("planning/")
    assert "content" in body
    c = body["content"]
    assert "M0.2" in c or "roadmap" in c.lower()


def test_api_planning_file_rejects_parent_segments(
    api_client: TestClient,
) -> None:
    r = api_client.get(
        "/api/planning/file",
        params={"path": "planning/../roadmap/manifest.json"},
    )
    assert r.status_code == 400


def test_api_planning_file_requires_under_planning(
    api_client: TestClient,
) -> None:
    r = api_client.get(
        "/api/planning/file",
        params={"path": "constraints/file-limits.yaml"},
    )
    assert r.status_code == 400


def test_api_workspace_upload_shared_ok(
    api_client: TestClient,
    dogfood_copy: Path,
) -> None:
    payload = {
        "path": "shared/pytest-gui-upload.bin",
        "content_base64": base64.b64encode(b"hello-gui").decode("ascii"),
    }
    r = api_client.post("/api/workspace/upload", json=payload)
    assert r.status_code == 200
    out = dogfood_copy / "shared" / "pytest-gui-upload.bin"
    assert out.read_bytes() == b"hello-gui"


def test_api_workspace_upload_rejects_non_shared(
    api_client: TestClient,
) -> None:
    payload = {
        "path": "work/oops.bin",
        "content_base64": base64.b64encode(b"x").decode("ascii"),
    }
    r = api_client.post("/api/workspace/upload", json=payload)
    assert r.status_code == 400


def test_api_workspace_upload_rejects_invalid_base64(
    api_client: TestClient,
) -> None:
    bad = "not!!!valid-base64"
    payload = {"path": "shared/bad.bin", "content_base64": bad}
    r = api_client.post("/api/workspace/upload", json=payload)
    assert r.status_code == 400
