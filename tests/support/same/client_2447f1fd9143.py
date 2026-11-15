"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from starlette.testclient import TestClient

def _client() -> TestClient:
    from specy_road.gui_app import create_app

    return TestClient(create_app())
