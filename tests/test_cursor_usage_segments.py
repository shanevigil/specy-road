"""M15.27: Cursor turn usage and possible-undercount marking."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True

from tests.test_worker_adapters import CURSOR_RESULT
from tests.worker_repo_helpers import make_worker_repo, reset_cursor_adapter_via_init, run_fake_harness_turn

from specy_road import worker_state as ws
from specy_road.worker_adapter_cursor import sum_cursor_turn_usage
from specy_road.worker_adapter_parsers import usage_fields
from specy_road.worker_usage_plausibility import (
    MIN_OUTPUT_TOKENS_PER_MINUTE,
    MIN_TURN_DURATION_FOR_UNDERCOUNT_SEC,
    possible_undercount,
)

FIXTURE = Path(__file__).parent / "fixtures/worker_usage/cursor_multi_segment_turn.json"
_SAN = Path(__file__).parent / "fixtures/worker_usage/sanitize_cursor_worker_log_turn.py"
_sanitize = importlib.util.spec_from_file_location("sanitize_cursor_worker_log_turn", _SAN)
assert _sanitize and _sanitize.loader
_smod = importlib.util.module_from_spec(_sanitize)
_sanitize.loader.exec_module(_smod)
excerpt_turn = _smod.excerpt_turn
expected_output_tokens = _smod.expected_output_tokens


def test_sanitize_excerpt_turn_keeps_every_usage_bearing_line_in_order() -> None:
    raw = [
        (1, {"type": "system", "subtype": "init", "session_id": "s", "model": "m"}),
        (2, {"type": "usage", "session_id": "s", "usage": {"outputTokens": 11, "inputTokens": 1}}),
        (3, {"type": "assistant", "session_id": "s", "message": {"usage": {"outputTokens": 13, "inputTokens": 1}}}),
        (4, {"type": "result", "subtype": "success", "session_id": "s", "usage": {"outputTokens": 17, "inputTokens": 1}}),
    ]
    excerpt = excerpt_turn(raw, 1, 4)
    assert [ln["type"] for ln in excerpt] == ["system", "usage", "assistant", "result"]
    assert expected_output_tokens(excerpt) == 41


def test_the_real_fixture_has_one_usage_bearing_line_and_pins_result_output_tokens() -> None:
    spec = json.loads(FIXTURE.read_text())
    assert spec["usage_bearing_lines"] == 1
    assert spec["expected_output_tokens"] == 44158
    result = next(ln for ln in spec["lines"] if ln["type"] == "result")
    assert usage_fields(result["usage"])["output_tokens"] == spec["expected_output_tokens"]


def test_cursor_parse_sums_when_intermediate_usage_lines_exist() -> None:
    cu = reset_cursor_adapter_via_init()
    cu.parse(json.dumps({"type": "system", "subtype": "init", "session_id": "s"}))
    cu.parse(json.dumps({"type": "usage", "session_id": "s", "usage": {"outputTokens": 11, "inputTokens": 1}}))
    cu.parse(json.dumps({"type": "assistant", "session_id": "s",
                          "message": {"usage": {"outputTokens": 13, "inputTokens": 1}}}))
    usage = cu.parse(json.dumps({"type": "result", "subtype": "success", "session_id": "s",
                                 "usage": {"outputTokens": 17, "inputTokens": 1}})).usage
    assert usage["output_tokens"] == 41


def test_a_single_result_with_num_turns_keeps_the_count() -> None:
    cu = reset_cursor_adapter_via_init()
    usage = cu.parse(json.dumps({**CURSOR_RESULT, "num_turns": 4, "session_id": "s"})).usage
    assert usage["output_tokens"] == 25 and usage["num_turns"] == 4


def test_the_fixture_turn_records_result_usage_in_the_worker(tmp_path: Path) -> None:
    spec = json.loads(FIXTURE.read_text())
    lines = [{**ln, "session_id": "s-1"} for ln in spec["lines"]]
    repo, script = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "cursor", "composer-2.5", repo)
    reset_cursor_adapter_via_init()
    run_fake_harness_turn(repo, script, rec, lines)
    usage = next(e.detail for e in ws.events_since(repo, rec.worker_id) if e.type == "usage")
    assert usage["output_tokens"] == spec["expected_output_tokens"]


def test_possible_undercount_flags_the_adopter_shape_and_not_a_short_rich_turn() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    long_usage = start + timedelta(seconds=6092)
    short_usage = start + timedelta(seconds=300)
    long_turn = [
        {"at": start.isoformat(), "type": "started", "source": "worker"},
        {"at": long_usage.isoformat(), "type": "usage", "source": "worker",
         "detail": {"output_tokens": 10136}},
    ]
    short_turn = [
        {"at": start.isoformat(), "type": "started", "source": "worker"},
        {"at": short_usage.isoformat(), "type": "usage", "source": "worker",
         "detail": {"output_tokens": 17000}},
    ]
    assert MIN_TURN_DURATION_FOR_UNDERCOUNT_SEC == 20 * 60
    assert MIN_OUTPUT_TOKENS_PER_MINUTE == 300
    assert possible_undercount(long_turn)
    assert not possible_undercount(short_turn)


def test_worker_usage_json_and_text_mark_possible_undercount() -> None:
    from specy_road.bundled_scripts import worker_cli_render as wcr

    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    events = [
        {"at": start.isoformat(), "type": "started", "source": "worker", "seq": 1},
        {"at": (start + timedelta(seconds=6092)).isoformat(), "type": "usage", "source": "worker", "seq": 2,
         "detail": {"input_tokens": 1, "output_tokens": 10136, "cached_input_tokens": None, "reasoning_tokens": None,
                    "cost_usd": None, "cost_is_estimate": None, "num_turns": None, "harness_version": None}},
    ]
    rec = type("R", (), {"attempt": 1, "worker_id": "w-0001", "model": "c", "harness": "cursor", "node_id": "M1.1",
                        "worktree": None})()
    data = wcr.usage([(rec, events)])
    assert data["attempts"][0]["possible_undercount"] is True
    assert data["total"]["possible_undercount"] is True
    lines = wcr.usage_lines(data)
    assert any("possible undercount" in ln for ln in lines)


def _reviewer_subtotal() -> dict:
    return {"runs": 1, "turns": 1, "input_tokens": 50, "output_tokens": 5, "cached_input_tokens": None,
            "reasoning_tokens": None, "cost_usd": 0.1, "cost_is_estimate": True, "num_turns": None}


def _usage_events(output_tokens: int, *, duration_sec: int) -> list[dict]:
    start = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    return [
        {"at": start.isoformat(), "type": "started", "source": "worker", "seq": 1},
        {"at": (start + timedelta(seconds=duration_sec)).isoformat(), "type": "usage", "source": "worker", "seq": 2,
         "detail": {"input_tokens": 1, "output_tokens": output_tokens, "cached_input_tokens": None,
                    "reasoning_tokens": None, "cost_usd": None, "cost_is_estimate": None, "num_turns": None,
                    "harness_version": None}},
    ]


def _worker_rec() -> object:
    return type("R", (), {"attempt": 1, "worker_id": "w-0001", "model": "c", "harness": "cursor", "node_id": "M1.1",
                         "worktree": None})()


def test_combined_usage_json_and_text_keep_possible_undercount_when_executor_is_flagged(monkeypatch) -> None:
    from specy_road.bundled_scripts import worker_cli_render as wcr

    monkeypatch.setattr(wcr, "reviewer_total", lambda data, repo_root=None: _reviewer_subtotal())
    data = wcr.usage([(_worker_rec(), _usage_events(10136, duration_sec=6092))])
    payload = wcr.usage_json_payload(data, Path("/tmp/repo"))
    assert payload["executors"]["possible_undercount"] is True
    assert payload["total"]["possible_undercount"] is True
    lines = wcr.usage_lines(data, Path("/tmp/repo"))
    assert "possible undercount" in lines[-1]


def test_combined_usage_omits_possible_undercount_when_executor_and_reviewer_are_unmarked(monkeypatch) -> None:
    from specy_road.bundled_scripts import worker_cli_render as wcr

    monkeypatch.setattr(wcr, "reviewer_total", lambda data, repo_root=None: _reviewer_subtotal())
    data = wcr.usage([(_worker_rec(), _usage_events(17000, duration_sec=300))])
    payload = wcr.usage_json_payload(data, Path("/tmp/repo"))
    assert "possible_undercount" not in payload["executors"]
    assert "possible_undercount" not in payload["total"]
    assert "possible undercount" not in wcr.usage_lines(data, Path("/tmp/repo"))[-1]


def test_reviewer_only_subtotal_does_not_imply_possible_undercount(monkeypatch) -> None:
    from specy_road.bundled_scripts import worker_cli_render as wcr

    monkeypatch.setattr(wcr, "reviewer_total", lambda data, repo_root=None: _reviewer_subtotal())
    data = wcr.usage([(_worker_rec(), [])])
    payload = wcr.usage_json_payload(data, Path("/tmp/repo"))
    assert "possible_undercount" not in payload.get("total", {})
