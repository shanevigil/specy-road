"""Claude Code's limit wording, pinned to checked-in fixtures.

If Anthropic changes the format, these fail. That is the point: the alternative
is an unattended grind that stalls or gives up without anyone knowing why.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from specy_road.claude_code_limits import (
    NONE,
    SPEND,
    TIMED,
    UNRECOGNIZED,
    classify_limit,
    parse_reset_at,
    parse_session_id,
    unrecognized_message,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "claude_code_limits"
NOW = datetime(2026, 9, 6, 20, 0, tzinfo=timezone.utc)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_a_timed_session_limit_is_recognized_and_dated() -> None:
    verdict = classify_limit(_fixture("timed_session_limit.txt"), now=NOW)

    assert verdict.kind == TIMED
    assert verdict.is_waitable
    # 1:20am Amsterdam (UTC+2 in September) is 23:20 UTC the evening before.
    assert verdict.reset_at == datetime(2026, 9, 6, 23, 20, tzinfo=timezone.utc)
    assert verdict.session_id == "3f2c9a7e-15b8-4d21-9c44-77aa10bd3e50"


def test_an_explicit_utc_reset_is_read_as_utc() -> None:
    verdict = classify_limit(_fixture("timed_limit_utc.txt"), now=NOW)

    assert verdict.reset_at == datetime(2026, 9, 6, 23, 0, tzinfo=timezone.utc)


def test_a_reset_without_a_timezone_falls_back_to_utc() -> None:
    verdict = classify_limit(_fixture("timed_limit_no_timezone.txt"), now=NOW)

    assert verdict.kind == TIMED
    assert verdict.reset_at == datetime(2026, 9, 7, 15, 5, tzinfo=timezone.utc)


def test_a_reset_already_past_today_means_tomorrow() -> None:
    """Read at 11pm, "resets 1:20am" is the next morning, not this one."""
    late = datetime(2026, 9, 6, 23, 0, tzinfo=timezone.utc)

    reset = parse_reset_at("resets 1:20am (UTC)", now=late)

    assert reset == datetime(2026, 9, 7, 1, 20, tzinfo=timezone.utc)


def test_a_spend_limit_is_not_something_to_wait_for() -> None:
    verdict = classify_limit(_fixture("monthly_spend_limit.txt"), now=NOW)

    assert verdict.kind == SPEND
    assert verdict.reset_at is None
    assert not verdict.is_waitable


def test_a_limit_we_cannot_parse_is_flagged_not_guessed() -> None:
    verdict = classify_limit(_fixture("unrecognized_limit.txt"), now=NOW)

    assert verdict.kind == UNRECOGNIZED
    assert "429" in verdict.evidence
    message = unrecognized_message(verdict)
    assert "output format may have changed" in message
    assert "429" in message


def test_ordinary_output_reports_no_limit() -> None:
    assert classify_limit(_fixture("no_limit.txt"), now=NOW).kind == NONE


def test_empty_output_reports_no_limit() -> None:
    assert classify_limit("", now=NOW).kind == NONE


def test_a_transcript_record_is_read_the_same_way() -> None:
    verdict = classify_limit(_fixture("transcript_records.jsonl"), now=NOW)

    assert verdict.kind == TIMED
    assert verdict.session_id == "3f2c9a7e-15b8-4d21-9c44-77aa10bd3e50"


@pytest.mark.parametrize(
    "text",
    ["resets 25:00am (UTC)", "resets 1:99am (UTC)", "resets soon", "resets 0:30am"],
)
def test_nonsense_clock_times_are_not_accepted(text: str) -> None:
    assert parse_reset_at(text, now=NOW) is None


def test_an_unknown_timezone_degrades_to_utc_rather_than_raising() -> None:
    reset = parse_reset_at("resets 4:00am (Mars/Olympus)", now=NOW)

    assert reset == datetime(2026, 9, 7, 4, 0, tzinfo=timezone.utc)


def test_no_session_id_is_reported_as_none() -> None:
    assert parse_session_id("nothing here") is None
