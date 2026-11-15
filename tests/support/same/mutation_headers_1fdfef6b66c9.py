"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from starlette.testclient import TestClient

def _mutation_headers(client: TestClient) -> dict[str, str]:
    r = client.get("/api/roadmap")
    assert r.status_code == 200
    return {"X-PM-Gui-Fingerprint": str(r.json()["fingerprint"])}
