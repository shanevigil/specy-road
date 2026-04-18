"""Process-local sliding-window RPM/TPM limits for OpenAI chat completions."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Callable

_SPECY_RPM = "SPECY_ROAD_LLM_RPM_MAX"
_SPECY_TPM = "SPECY_ROAD_LLM_TPM_MAX"
_AZURE_RPM = "AZURE_OPENAI_MAX_REQUESTS_PER_MINUTE"
_AZURE_TPM = "AZURE_OPENAI_MAX_TOKENS_PER_MINUTE"


class ThroughputExceeded(Exception):
    """Raised when the next request would exceed a configured RPM or TPM cap."""


def _parse_limit_int(raw: str, env_key: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        n = int(raw)
    except ValueError as e:
        raise ValueError(
            f"{env_key} must be a non-negative integer, got {raw!r}",
        ) from e
    if n < 0:
        raise ValueError(f"{env_key} must be non-negative, got {n}")
    if n == 0:
        return None
    return n


def _resolved_limit_raw(specy_key: str, azure_key: str) -> tuple[str, str]:
    """Return (effective_raw, env_key_for_errors): SPECY_ wins when non-empty."""
    specy = os.environ.get(specy_key, "")
    if specy.strip():
        return specy.strip(), specy_key
    az = os.environ.get(azure_key, "")
    if az.strip():
        return az.strip(), azure_key
    return "", ""


def parse_openai_chat_throughput_limits() -> tuple[int | None, int | None]:
    """
    (rpm_max, tpm_max) for the rolling window; ``None`` means unlimited for that axis.

    ``SPECY_ROAD_LLM_RPM_MAX`` / ``SPECY_ROAD_LLM_TPM_MAX`` win when non-empty;
    otherwise ``AZURE_OPENAI_MAX_REQUESTS_PER_MINUTE`` /
    ``AZURE_OPENAI_MAX_TOKENS_PER_MINUTE``. Empty or ``0`` disables that axis.
    """
    raw_r, key_r = _resolved_limit_raw(_SPECY_RPM, _AZURE_RPM)
    raw_t, key_t = _resolved_limit_raw(_SPECY_TPM, _AZURE_TPM)
    rpm = _parse_limit_int(raw_r, key_r) if raw_r else None
    tpm = _parse_limit_int(raw_t, key_t) if raw_t else None
    return rpm, tpm


def estimate_openai_chat_request_tokens(**kwargs: object) -> int:
    """Rough token estimate from chat completion kwargs (no logging)."""
    parts: list[str] = []
    m = kwargs.get("model")
    if m is not None:
        parts.append(str(m))
    messages = kwargs.get("messages")
    if isinstance(messages, list):
        for item in messages:
            if not isinstance(item, dict):
                parts.append(str(item))
                continue
            role = item.get("role", "")
            parts.append(str(role))
            content = item.get("content", "")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        parts.append(str(block.get("type", "")))
                        if "text" in block:
                            parts.append(str(block.get("text", "")))
                        else:
                            parts.append(str(block.get("content", "")))
                    else:
                        parts.append(str(block))
            else:
                parts.append(str(content))
    for k in ("max_tokens", "max_completion_tokens", "temperature", "top_p"):
        if k in kwargs and kwargs[k] is not None:
            parts.append(str(kwargs[k]))
    total_chars = sum(len(s.encode("utf-8")) for s in parts)
    return max(1, total_chars // 4)


class OpenAiChatThroughputGate:
    """Sliding-window request count and token sum (process-local)."""

    def __init__(
        self,
        *,
        now_fn: Callable[[], float] | None = None,
        window_seconds: float = 60.0,
    ) -> None:
        self._now_fn = now_fn or time.monotonic
        self._window = window_seconds
        self._lock = threading.Lock()
        self._events: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self._window
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()

    def reserve(
        self,
        *,
        rpm_max: int | None,
        tpm_max: int | None,
        token_estimate: int,
    ) -> None:
        if rpm_max is None and tpm_max is None:
            return
        est = max(1, int(token_estimate))
        with self._lock:
            now = self._now_fn()
            self._prune(now)
            if rpm_max is not None and len(self._events) >= rpm_max:
                raise ThroughputExceeded(
                    "LLM throughput limit: request rate cap reached for the "
                    f"configured rolling {int(self._window)}s window (RPM). "
                    "Wait and retry, or raise SPECY_ROAD_LLM_RPM_MAX / "
                    f"{_AZURE_RPM}.",
                )
            if tpm_max is not None:
                used = sum(t for _, t in self._events)
                if used + est > tpm_max:
                    raise ThroughputExceeded(
                        "LLM throughput limit: estimated token budget for the "
                        f"next call would exceed the configured rolling "
                        f"{int(self._window)}s window (TPM). Wait and retry, or "
                        f"raise SPECY_ROAD_LLM_TPM_MAX / {_AZURE_TPM}.",
                    )
            self._events.append((now, est))

    def adjust_last_reservation(self, actual_total_tokens: int | None) -> None:
        """Replace the last reserved token count when usage is known."""
        if actual_total_tokens is None:
            return
        act = int(actual_total_tokens)
        if act < 1:
            act = 1
        with self._lock:
            if not self._events:
                return
            ts, _ = self._events[-1]
            self._events[-1] = (ts, act)


_gate: OpenAiChatThroughputGate | None = None
_gate_lock = threading.Lock()


def get_openai_chat_throughput_gate() -> OpenAiChatThroughputGate:
    global _gate
    with _gate_lock:
        if _gate is None:
            _gate = OpenAiChatThroughputGate()
        return _gate


def reset_openai_chat_throughput_gate_for_tests() -> None:
    """Clear singleton and internal state (unit tests only)."""
    global _gate
    with _gate_lock:
        _gate = None
