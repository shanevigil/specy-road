"""Two concurrent PATCHes for one node: the second is refused with 409 (F1, rc3 runbook)."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.helpers import DOGFOOD


@pytest.fixture()
def dogfood_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dest = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dest)
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dest))
    return dest


def _client() -> TestClient:
    from specy_road.gui_app import create_app

    return TestClient(create_app())


def _patch_title(client: TestClient, token: str, title: str):
    return client.patch(
        "/api/nodes/M2",
        headers={"X-PM-Gui-Fingerprint": token, "Content-Type": "application/json"},
        json={"pairs": [{"key": "title", "value": title}]},
    )


def test_second_concurrent_rename_is_refused_with_409(
    dogfood_copy: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import specy_road.gui_app_routes_nodes as routes

    entered, release = threading.Event(), threading.Event()
    real_edit = routes.edit_node_set_pairs

    def slow_edit(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return real_edit(*args, **kwargs)

    monkeypatch.setattr(routes, "edit_node_set_pairs", slow_edit)
    client = _client()
    token = str(client.get("/api/roadmap").json()["fingerprint"])
    first: dict[str, object] = {}
    t = threading.Thread(
        target=lambda: first.update(r=_patch_title(client, token, "Test harness checks")),
    )
    t.start()
    assert entered.wait(10)
    # Same token, same title: what the dialog sent twice for one edit.
    second = _patch_title(client, token, "Test harness checks")
    release.set()
    t.join(10)

    assert second.status_code == 409, second.text
    assert "still running" in second.json()["detail"]["message"]
    assert first["r"].status_code == 200, first["r"].text
    # One renamed sheet, and the roadmap points at it: no orphan, no missing file.
    sheets = sorted(p.name for p in (dogfood_copy / "planning").glob("M2_*.md"))
    assert sheets == ["M2_test-harness-checks_4c1d98f2-2bdc-4a7d-81b9-c6f7e96e95f0.md"]
    node = next(n for n in client.get("/api/roadmap").json()["nodes"] if n["id"] == "M2")
    assert node["planning_dir"] == f"planning/{sheets[0]}"


def test_write_after_the_slot_frees_needs_the_new_token(dogfood_copy: Path) -> None:
    client = _client()
    token = str(client.get("/api/roadmap").json()["fingerprint"])
    assert _patch_title(client, token, "Test harness checks").status_code == 200
    stale = _patch_title(client, token, "Test harness checks")
    assert stale.status_code == 412, stale.text
    fresh = str(client.get("/api/roadmap").json()["fingerprint"])
    assert _patch_title(client, fresh, "testing").status_code == 200
