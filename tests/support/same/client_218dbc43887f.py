"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from starlette.testclient import TestClient
import pytest

@pytest.fixture()
def client(repo: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(repo))
    from specy_road.gui_app import create_app

    return TestClient(create_app())
