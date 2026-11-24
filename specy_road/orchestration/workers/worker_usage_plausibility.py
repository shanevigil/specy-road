"""Heuristics for Cursor (and other) worker turns whose reported usage looks implausibly low."""

from __future__ import annotations

from datetime import datetime

#: A turn at least this long (seconds from harness ``started`` to its ``usage`` event) may be flagged.
MIN_TURN_DURATION_FOR_UNDERCOUNT_SEC = 20 * 60
#: Below this average output tokens per minute over that duration, the turn is a possible undercount.
MIN_OUTPUT_TOKENS_PER_MINUTE = 300


def _parse_at(at: str) -> datetime:
    return datetime.fromisoformat(at.replace("Z", "+00:00"))


def _turn_start_at(events: list[dict], usage_index: int) -> str | None:
    """The harness ``started`` event before this ``usage`` event (same worker turn)."""
    for e in reversed(events[:usage_index]):
        if e.get("type") == "started" and e.get("source") == "worker":
            return e["at"]
    return None


def possible_undercount(events: list[dict]) -> bool:
    """True when some ``usage`` event in ``events`` looks too small for how long the turn ran."""
    for i, e in enumerate(events):
        if e.get("type") != "usage":
            continue
        detail = e.get("detail") or {}
        out = detail.get("output_tokens")
        if out is None:
            continue
        start = _turn_start_at(events, i)
        if not start:
            continue
        mins = (_parse_at(e["at"]) - _parse_at(start)).total_seconds() / 60
        if mins <= 0:
            continue
        if (_parse_at(e["at"]) - _parse_at(start)).total_seconds() >= MIN_TURN_DURATION_FOR_UNDERCOUNT_SEC:
            if out / mins < MIN_OUTPUT_TOKENS_PER_MINUTE:
                return True
    return False
