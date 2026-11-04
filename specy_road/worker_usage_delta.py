"""One turn's share of a harness's running session totals, for the turn's ``usage`` event.

Split from :mod:`specy_road.worker_runner` for the file limit. Some harnesses report the session's running total
instead of the turn's: Claude Code's ``total_cost_usd`` (recorded as ``session_cost_usd``), and the token counts of
``codex exec resume``'s ``turn.completed`` (recorded as ``session_usage``). The turn's figure is the difference from
the worker's previous ``usage`` event that carried the same total, so ``worker usage`` can sum the turns. A total
lower than the previous one is a new session (a custom command without one) and counts whole.
"""

from __future__ import annotations

from typing import Any

from specy_road.worker_state import WorkerEvent

#: The token counts a ``session_usage`` total carries.
SESSION_TOKENS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens")


def _last(events: list[WorkerEvent], key: str) -> Any:
    return next((e.detail[key] for e in reversed(events) if e.type == "usage" and (e.detail or {}).get(key) is not None),
                None)


def _grew(prev: dict[str, Any], now: dict[str, Any]) -> bool:
    """True when every count ``prev`` reported is reported in ``now`` and is not lower: the same session."""
    return all(prev.get(k) is None or (now.get(k) is not None and now[k] >= prev[k]) for k in SESSION_TOKENS)


def turn_usage(detail: dict[str, Any], events: list[WorkerEvent]) -> dict[str, Any]:
    """``detail`` with ``cost_usd`` and the token counts made this turn's, given the worker's earlier ``events``."""
    out = dict(detail)
    total = out.get("session_cost_usd")
    if total is not None:
        prev = _last(events, "session_cost_usd")
        out["cost_usd"] = round(total - prev, 6) if prev is not None and prev <= total else total
    now, before = out.get("session_usage"), _last(events, "session_usage")
    if isinstance(now, dict) and isinstance(before, dict) and _grew(before, now):
        out.update({k: now[k] - (before.get(k) or 0) for k in SESSION_TOKENS if now.get(k) is not None})
    return out
