from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD


def _expected_gui_repo_id(path: Path) -> str:
    """Matches ``repo_settings_id`` / ``gui-settings.json`` project keys."""
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()


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


def _mutation_headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/roadmap")
    assert r.status_code == 200
    return {"X-PM-Gui-Fingerprint": str(r.json()["fingerprint"])}


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
    assert r.json()["repo_id"] == _expected_gui_repo_id(dogfood_copy)
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
    assert r.json()["repo_id"] == _expected_gui_repo_id(dogfood_copy)
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
    assert "git_workflow" in data
    gw = data["git_workflow"]
    assert "ok" in gw and "issues" in gw and "resolved" in gw
    assert "git_user_name" in gw["resolved"]
    assert "registry_visibility" not in data
    assert "registry" in data and isinstance(data["registry"], dict)
    assert "registry_by_node" in data and isinstance(data["registry_by_node"], dict)
    assert data["registry"].get("entries") == []
    assert data["registry_by_node"] == {}


def test_api_roadmap_registry_by_node_reflects_merged_registry(
    dogfood_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PM UI keys rows by display id via registry_by_node; must track merged overlay registry."""
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))
    fake_entry = {
        "codename": "api-test",
        "node_id": "M1",
        "branch": "feature/rm-api-test",
        "touch_zones": ["tests/"],
    }
    merged = {"version": 1, "entries": [fake_entry]}
    meta = {
        "enabled": True,
        "remote": "origin",
        "remote_refs_scanned": 1,
        "merged_remote_entries": 1,
        "skipped_refs": 0,
    }

    def fake_merge(_head: dict, _root: Path) -> tuple[dict, dict]:
        return merged, meta

    monkeypatch.setattr(
        "specy_road.gui_app_routes_core.registry_remote_overlay_enabled",
        lambda _r: True,
    )
    monkeypatch.setattr(
        "specy_road.gui_app_routes_core.merge_registry_with_remote_overlay",
        fake_merge,
    )
    monkeypatch.setattr(
        "specy_road.gui_app_routes_core.maybe_auto_git_fetch",
        lambda *_a, **_kw: None,
    )
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r = client.get("/api/roadmap")
    assert r.status_code == 200
    data = r.json()
    assert data["registry"] == merged
    rb = data["registry_by_node"]
    assert rb["M1"]["branch"] == "feature/rm-api-test"
    assert rb["M1"]["codename"] == "api-test"
    ov = data.get("registry_overlay")
    assert isinstance(ov, dict)
    assert ov.get("merged_remote_entries") == 1


def test_api_roadmap_includes_registry_overlay_when_enabled(
    dogfood_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))
    monkeypatch.delenv("SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY", raising=False)

    def _force_overlay(_root):
        return True

    monkeypatch.setattr(
        "specy_road.gui_app_routes_core.registry_remote_overlay_enabled",
        _force_overlay,
    )
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r = client.get("/api/roadmap")
    assert r.status_code == 200
    ov = r.json().get("registry_overlay")
    assert isinstance(ov, dict)
    assert ov.get("enabled") is True
    assert "remote_refs_scanned" in ov


def test_api_roadmap_includes_last_auto_fetch_attempt_in_overlay_meta(
    dogfood_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))
    monkeypatch.setattr(
        "specy_road.gui_app_routes_core.registry_remote_overlay_enabled",
        lambda _r: True,
    )
    monkeypatch.setattr(
        "specy_road.gui_app_routes_core.merge_registry_with_remote_overlay",
        lambda _head, _root: (
            {"version": 1, "entries": []},
            {"enabled": True, "remote_refs_scanned": 0},
        ),
    )
    monkeypatch.setattr(
        "specy_road.gui_app_routes_core.maybe_auto_git_fetch",
        lambda *_a, **_kw: None,
    )
    monkeypatch.setattr(
        "specy_road.gui_app_routes_core.last_registry_auto_fetch_status",
        lambda _r: {
            "ok": False,
            "reason": "non_zero_exit",
            "step": "fetch",
            "remote": "origin",
        },
    )
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r = client.get("/api/roadmap")
    assert r.status_code == 200
    ov = r.json().get("registry_overlay")
    assert isinstance(ov, dict)
    last = ov.get("last_auto_fetch_attempt")
    assert isinstance(last, dict)
    assert last.get("ok") is False
    assert last.get("reason") == "non_zero_exit"


def test_api_git_workflow_status(api_client: TestClient) -> None:
    r = api_client.get("/api/git-workflow-status")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body
    assert isinstance(body.get("issues"), list)


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


def test_api_planning_file_reads_repo_root_vision(api_client: TestClient) -> None:
    r = api_client.get(
        "/api/planning/file",
        params={"path": "vision.md"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "vision.md"
    assert "content" in body
    assert len(body["content"]) > 0


def test_api_planning_file_reads_constitution(api_client: TestClient) -> None:
    r = api_client.get(
        "/api/planning/file",
        params={"path": "constitution/purpose.md"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "constitution/purpose.md"
    assert "content" in body


def test_api_planning_file_rejects_parent_segments(
    api_client: TestClient,
) -> None:
    r = api_client.get(
        "/api/planning/file",
        params={"path": "planning/../roadmap/manifest.json"},
    )
    assert r.status_code == 400


def test_api_planning_file_rejects_disallowed_paths(
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
    r = api_client.post(
        "/api/workspace/upload",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json=payload,
    )
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
    r = api_client.post(
        "/api/workspace/upload",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json=payload,
    )
    assert r.status_code == 400


def test_api_workspace_upload_rejects_invalid_base64(
    api_client: TestClient,
) -> None:
    bad = "not!!!valid-base64"
    payload = {"path": "shared/bad.bin", "content_base64": bad}
    r = api_client.post(
        "/api/workspace/upload",
        headers={
            **_mutation_headers(api_client),
            "Content-Type": "application/json",
        },
        json=payload,
    )
    assert r.status_code == 400
