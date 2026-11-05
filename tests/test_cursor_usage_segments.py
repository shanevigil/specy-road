"""M15.27: Cursor multi-segment usage sums and possible-undercount marking."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.test_worker_adapters import CURSOR_RESULT
from tests.test_worker_cli import _turn
from tests.worker_repo_helpers import make_worker_repo

from specy_road import worker_adapters as wa
from specy_road import worker_state as ws
from specy_road.worker_adapter_cursor import combine_cursor_turn_usage
from specy_road.worker_usage_plausibility import (
    MIN_OUTPUT_TOKENS_PER_MINUTE,
    MIN_TURN_DURATION_FOR_UNDERCOUNT_SEC,
    possible_undercount,
)

FIXTURE = Path(__file__).parent / "fixtures/worker_usage/cursor_multi_segment_turn.json"


def test_combine_cursor_turn_usage_sums_per_segment_counts_when_the_last_is_not_a_running_total() -> None:
    segments = [
        {"output_tokens": 7200, "input_tokens": 100},
        {"output_tokens": 8400, "input_tokens": 100},
        {"output_tokens": 6500, "input_tokens": 100},
        {"output_tokens": 10136, "input_tokens": 100},
    ]
    assert combine_cursor_turn_usage(segments)["output_tokens"] == 32236


def test_combine_cursor_turn_usage_keeps_a_single_short_turn_unchanged() -> None:
    cu = wa.adapter_for("cursor")
    cu._usage_segments = []  # singleton adapter: isolate from other tests
    one = cu.parse(json.dumps(CURSOR_RESULT)).usage
    assert one["output_tokens"] == 25
    assert combine_cursor_turn_usage([one]) == one


def test_a_multi_segment_cursor_turn_records_the_sum_of_every_usage_line(tmp_path: Path) -> None:
    """Every usage-bearing stream line counts; worker usage matches the fixture total, not the last segment alone."""
    spec = json.loads(FIXTURE.read_text())
    lines = [{**ln, "session_id": "s-1"} for ln in spec["lines"]]
    repo, script = make_worker_repo(tmp_path)
    rec = ws.create_record(repo, "M1.1", "cursor", "composer-2.5", repo)
    wa.adapter_for("cursor")._usage_segments = []
    _turn(repo, script, rec, lines)
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
