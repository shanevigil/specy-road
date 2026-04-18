"""Regression coverage for two field-reproduced bugs in PM GUI mutating routes.

Bug 1 — JS Number precision on fingerprint
   The optimistic-concurrency token routinely exceeds ``2**53`` (it's a
   sum of ``mtime_ns`` values). When the server emits it as a JSON
   number the browser's ``JSON.parse`` rounds to the nearest IEEE 754
   ``Number``, then ``String(n)`` round-trips a slightly different
   value back as ``X-PM-Gui-Fingerprint``. The server's exact int never
   matches → 412 every request, regardless of what's on disk. Fix:
   string-encode fingerprints end-to-end.

Bug 2 — ``rollup_status`` rejected by older consumer schemas
   ``load_roadmap`` annotates each in-memory node with a derived
   ``rollup_status`` field. The on-disk chunk JSON never carries it,
   but the in-memory roadmap document does. ``run_validation`` then
   passed that document to ``validate_schema`` against the
   consumer-side ``schemas/roadmap.schema.json``, which (for older
   schemas) does not list ``rollup_status`` as an allowed property
   and rejects the document with "Additional properties are not
   allowed (\\'rollup_status\\' was unexpected)". Fix: strip derived
   keys before schema validation.
"""

from __future__ import annotations

import json

import pytest

from tests.test_pm_gui_concurrency_autoff import (  # noqa: F401 — fixture import
    _siblings_of,
    autoff_repo,
)


def test_fingerprint_emitted_as_string_to_dodge_js_number_precision(
    autoff_repo,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server must emit ``fingerprint`` (and ``view_fingerprint``) as JSON
    strings so the browser's ``Number`` type cannot lose precision when
    the client forwards the value as ``X-PM-Gui-Fingerprint``."""
    work, _ = autoff_repo
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(work))
    from starlette.testclient import TestClient

    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    rm = client.get("/api/roadmap").json()
    assert isinstance(rm["fingerprint"], str), (
        "fingerprint must be a JSON string to dodge JS Number precision"
    )
    assert rm["fingerprint"].lstrip("-").isdigit()
    assert isinstance(rm["view_fingerprint"], str)

    fp_endpoint = client.get("/api/roadmap/fingerprint").json()
    assert isinstance(fp_endpoint["fingerprint"], str)
    assert fp_endpoint["fingerprint"] == rm["fingerprint"]

    sibs = _siblings_of(work, "M0")
    rotated = sibs[-1:] + sibs[:-1]
    r = client.post(
        "/api/outline/reorder",
        headers={"X-PM-Gui-Fingerprint": rm["fingerprint"]},
        json={"parent_id": "M0", "ordered_child_ids": rotated},
    )
    assert r.status_code == 200, r.text


def test_mutation_does_not_412_on_rollup_status_in_validate(
    autoff_repo,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the roadmap schema to a version that does NOT allow
    ``rollup_status``, then attempt a reorder. Must succeed because
    derived fields are stripped before schema validation."""
    work, _ = autoff_repo
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(work))
    schema_path = work / "schemas" / "roadmap.schema.json"
    doc = json.loads(schema_path.read_text(encoding="utf-8"))

    def _scrub_rollup(obj: object) -> None:
        if isinstance(obj, dict):
            obj.pop("rollup_status", None)
            for v in obj.values():
                _scrub_rollup(v)
        elif isinstance(obj, list):
            for v in obj:
                _scrub_rollup(v)

    _scrub_rollup(doc)
    schema_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    from starlette.testclient import TestClient

    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    fp = client.get("/api/roadmap").json()["fingerprint"]
    sibs = _siblings_of(work, "M0")
    rotated = sibs[-1:] + sibs[:-1]
    r = client.post(
        "/api/outline/reorder",
        headers={"X-PM-Gui-Fingerprint": fp},
        json={"parent_id": "M0", "ordered_child_ids": rotated},
    )
    assert r.status_code == 200, r.text
