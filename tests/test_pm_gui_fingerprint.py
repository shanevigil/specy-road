"""PM GUI mutation fingerprint includes planning/constitution/vision/shared paths."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD


@pytest.fixture()
def dogfood_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dest)
    return dest


def test_pm_gui_mutation_fingerprint_base_changes_when_planning_file_touched(
    dogfood_copy: Path,
) -> None:
    from roadmap_gui_lib import (
        iter_pm_gui_extra_fingerprint_files,
        pm_gui_mutation_fingerprint_base,
        roadmap_fingerprint,
    )

    a = pm_gui_mutation_fingerprint_base(dogfood_copy)
    b = roadmap_fingerprint(dogfood_copy)
    assert a >= b

    planning = dogfood_copy / "planning"
    planning.mkdir(parents=True, exist_ok=True)
    p = planning / "pytest_pm_gui_fp_touch.md"
    p.write_text("# touch\n", encoding="utf-8")
    assert p in iter_pm_gui_extra_fingerprint_files(dogfood_copy)
    c = pm_gui_mutation_fingerprint_base(dogfood_copy)
    assert c != a


def test_pm_gui_mutation_matches_fingerprint_endpoint(
    dogfood_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))
    from starlette.testclient import TestClient

    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r0 = client.get("/api/roadmap")
    assert r0.status_code == 200
    fp0 = r0.json()["fingerprint"]
    r1 = client.get("/api/roadmap/fingerprint")
    assert r1.status_code == 200
    assert r1.json()["fingerprint"] == fp0


def test_pm_gui_mutation_stale_fingerprint_returns_412(
    dogfood_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))
    from starlette.testclient import TestClient

    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r0 = client.get("/api/roadmap")
    fp = r0.json()["fingerprint"]
    r_ok = client.patch(
        "/api/nodes/M0.2",
        headers={"X-PM-Gui-Fingerprint": str(fp)},
        json={"pairs": [{"key": "title", "value": "ok fp"}]},
    )
    assert r_ok.status_code == 200
    r1 = client.get("/api/roadmap")
    fp2 = r1.json()["fingerprint"]
    assert fp2 != fp
    r_stale = client.patch(
        "/api/nodes/M0.2",
        headers={"X-PM-Gui-Fingerprint": str(fp)},
        json={"pairs": [{"key": "title", "value": "stale"}]},
    )
    assert r_stale.status_code == 412
    body = r_stale.json()
    assert "detail" in body
    det = body["detail"]
    assert isinstance(det, dict)
    assert "current_fingerprint" in det
    assert isinstance(det["current_fingerprint"], int)


def test_pm_gui_mutation_missing_header_returns_428(
    dogfood_copy: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))
    from starlette.testclient import TestClient

    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r = client.patch(
        "/api/nodes/M0.2",
        json={"pairs": [{"key": "title", "value": "x"}]},
    )
    assert r.status_code == 428
