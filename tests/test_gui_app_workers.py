"""M10.12: the PM GUI's read-only worker routes (GET /api/workers, GET /api/workers/{id}/events)."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from specy_road import worker_state as ws
from tests.review_repo_helpers import make_review_repo


def _usage(cost: float | None) -> dict:
    return {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10, "reasoning_tokens": None,
            "cost_usd": cost, "cost_is_estimate": True if cost is not None else None, "num_turns": 2,
            "harness_version": "2.1.0"}


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = make_review_repo(tmp_path)
    a = ws.create_record(root, "M1.1", "claude-code", "opus", root)
    for type_ in ("launched", "first_output"):
        ws.append_event(root, a, type_, source="system", summary=type_)
    ws.append_event(root, a, "output", source="worker", summary="(tool use)")
    ws.append_event(root, a, "stalled", source="system", summary="no output for 600s")
    ws.append_event(root, a, "usage", source="worker", summary="usage", detail=_usage(0.5))
    ws.append_event(root, a, "turn_completed", source="worker", summary="done")
    ws.append_event(root, a, "usage", source="worker", summary="usage", detail=_usage(0.25))
    ws.set_state(root, a, "failed", pid=None)
    ws.create_record(root, "M1.1", "codex", "sol", root)   # a second attempt that has reported nothing yet
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(root))
    return root


def _client() -> TestClient:
    from specy_road.gui_app import create_app

    return TestClient(create_app())


def _snapshot(root: Path) -> dict[str, bytes]:
    d = ws.workers_dir(root)
    return {str(p): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def test_list_has_one_row_per_worker_with_cost_and_last_event(repo: Path) -> None:
    r = _client().get("/api/workers")
    assert r.status_code == 200
    rows = r.json()["workers"]
    assert [(w["worker_id"], w["node_id"], w["harness"], w["model"], w["state"], w["attempt"]) for w in rows] == [
        ("w-0001", "M1.1", "claude-code", "opus", "failed", 1), ("w-0002", "M1.1", "codex", "sol", "starting", 2)]
    assert rows[0]["total_cost_usd"] == 0.75 and rows[0]["cost_is_estimate"] is True
    assert rows[0]["last_event"]["type"] == "usage" and rows[0]["last_event"]["seq"] == 8
    # No usage event: the cost is unknown, never 0.
    assert rows[1]["total_cost_usd"] is None and rows[1]["last_event"]["type"] == "started"


def test_events_route_returns_log_phases_and_usage_totals(repo: Path) -> None:
    r = _client().get("/api/workers/w-0001/events")
    assert r.status_code == 200
    d = r.json()
    assert [e["type"] for e in d["events"]] == ["started", "launched", "first_output", "output", "stalled",
                                                 "usage", "turn_completed", "usage"]
    assert list(d["phases"]) == ["delegated_to_launched", "launched_to_first_output", "first_output_to_end",
                                 "end_to_acked"]
    assert all(isinstance(d["phases"][k], float) for k in list(d["phases"])[:3])
    assert d["phases"]["end_to_acked"] is None   # never acked
    assert d["usage"]["cost_usd"] == 0.75 and d["usage"]["input_tokens"] == 200 and d["usage"]["turns"] == 2
    assert d["usage"]["reasoning_tokens"] is None


def test_unknown_or_malformed_worker_id_is_404(repo: Path) -> None:
    c = _client()
    assert c.get("/api/workers/w-9999/events").status_code == 404
    assert c.get("/api/workers/sync/events").status_code == 404


def test_routes_never_write_the_workers_directory(repo: Path) -> None:
    before = _snapshot(repo)
    c = _client()
    assert c.get("/api/workers").status_code == 200
    assert c.get("/api/workers/w-0001/events").status_code == 200
    assert _snapshot(repo) == before


def test_no_workers_directory_lists_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_review_repo(tmp_path)
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(root))
    assert _client().get("/api/workers").json() == {"workers": []}
    assert not ws.workers_dir(root).exists()
