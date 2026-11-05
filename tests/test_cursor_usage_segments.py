"""M15.27: Cursor multi-segment usage sums and possible-undercount marking."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.test_worker_adapters import CURSOR_RESULT
from tests.worker_repo_helpers import make_worker_repo, reset_cursor_adapter_via_init, run_fake_harness_turn

from specy_road import worker_adapters as wa
from specy_road import worker_state as ws
from specy_road.worker_adapter_cursor import combine_cursor_turn_usage, merge_cursor_result_usage
from specy_road.worker_usage_plausibility import (
    MIN_OUTPUT_TOKENS_PER_MINUTE,
    MIN_TURN_DURATION_FOR_UNDERCOUNT_SEC,
    possible_undercount,
)

FIXTURE = Path(__file__).parent / "fixtures/worker_usage/cursor_multi_segment_turn.json"


def _entry(out: int, *, session: bool = False) -> tuple[dict, str]:
    kind = "session" if session else "segment"
    return ({"output_tokens": out, "input_tokens": 1}, kind)


def test_combine_cursor_turn_usage_sums_per_segment_lines_even_when_outputs_increase() -> None:
    entries = [_entry(100), _entry(200), _entry(300)]
    assert combine_cursor_turn_usage(entries)["output_tokens"] == 600


def test_combine_cursor_turn_usage_keeps_a_session_marked_running_total_at_its_last_value() -> None:
    entries = [_entry(100, session=True), _entry(200, session=True), _entry(300, session=True)]
    out = combine_cursor_turn_usage(entries)
    assert out["output_tokens"] == 300
    assert out["session_usage"]["output_tokens"] == 300


def test_combine_cursor_turn_usage_sums_segments_then_applies_a_session_marked_line() -> None:
    entries = [_entry(1000), _entry(2000), _entry(5000, session=True)]
    out = combine_cursor_turn_usage(entries)
    assert out["output_tokens"] == 5000
    assert out["session_usage"]["output_tokens"] == 5000


def test_combine_cursor_turn_usage_sums_the_multi_segment_fixture_shape() -> None:
    spec = json.loads(FIXTURE.read_text())
    entries = [({"output_tokens": n, "input_tokens": 1}, "segment") for n in spec["segment_output_tokens"]]
    assert combine_cursor_turn_usage(entries)["output_tokens"] == spec["expected_output_tokens"]


def test_merge_cursor_result_usage_keeps_num_turns_from_the_result_line() -> None:
    one = ({"output_tokens": 25, "input_tokens": 1}, "segment")
    usage = merge_cursor_result_usage([one], {"num_turns": 4, "usage": {"outputTokens": 25}})
    assert usage["output_tokens"] == 25 and usage["num_turns"] == 4


def test_a_single_result_with_num_turns_keeps_the_count() -> None:
    cu = reset_cursor_adapter_via_init()
    line = {**CURSOR_RESULT, "num_turns": 4}
    usage = cu.parse(json.dumps(line)).usage
    assert usage["output_tokens"] == 25 and usage["num_turns"] == 4


def test_a_multi_segment_cursor_turn_records_the_sum_of_every_usage_line(tmp_path: Path) -> None:
    """Every usage-bearing stream line counts; worker usage matches the fixture total, not the last segment alone."""
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
