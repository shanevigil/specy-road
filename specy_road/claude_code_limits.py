"""Recognising Claude Code's usage-limit messages, and nothing else.

One vendor's output format, isolated behind one module with checked-in fixtures.
``grind-session`` waits out a timed session limit so an unattended run survives
one, and the only thing standing between "the loop continued" and "the loop
stalled silently" is whether this parser still recognises the wording. When
Anthropic changes it, :func:`classify_limit` returns ``UNRECOGNIZED`` and the
caller stops loudly. It must never guess.

Nothing here reaches the network or a model. It reads text a subprocess already
printed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: A limit that lifts at a stated clock time — the one kind worth waiting for.
TIMED = "timed"
#: A spend cap with no reset time. Waiting cannot help; say so and stop.
SPEND = "spend"
#: Looks like a limit, parsed like nothing. The format probably moved.
UNRECOGNIZED = "unrecognized"
#: No limit in this output at all.
NONE = "none"

#: "resets 1:20am (Europe/Amsterdam)" / "resets at 11pm (UTC)" / "resets 3:05 PM"
_RESET = re.compile(
    r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?"
    r"(?:\s*\(([^)]+)\))?",
    re.IGNORECASE,
)

#: Wording that says "you are rate limited" without saying when it lifts.
_LIMIT_HINT = re.compile(
    r"(usage limit|session limit|rate[- ]limit|limit reached|out of (?:usage|credits)"
    r"|429|too many requests|quota)",
    re.IGNORECASE,
)

#: Spend caps: no clock time exists, so no amount of waiting clears them.
_SPEND_HINT = re.compile(
    r"(monthly (?:spend|usage|limit)|spend(?:ing)? limit|credit balance"
    r"|billing|payment method|add (?:more )?credits|organization limit)",
    re.IGNORECASE,
)

#: Claude prints its own session id; grind needs it to resume the same session.
_SESSION_ID = re.compile(
    r"session[ _-]?id[\"'\s:=]+([0-9a-fA-F-]{8,64})", re.IGNORECASE
)


@dataclass(frozen=True)
class LimitVerdict:
    """What the implement command's output said about usage limits."""

    kind: str
    reset_at: datetime | None = None
    session_id: str | None = None
    #: The line that produced this verdict, for the loud-failure message.
    evidence: str = ""

    @property
    def is_waitable(self) -> bool:
        return self.kind == TIMED and self.reset_at is not None


def _tz(name: str | None) -> timezone | ZoneInfo:
    if not name:
        return timezone.utc
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return timezone.utc


def _next_occurrence(hour: int, minute: int, tzinfo, now: datetime) -> datetime:
    """The next time the clock reads ``hour:minute`` in ``tzinfo``.

    A limit that resets at 1:20am, read at 11pm, lifts tomorrow — the wording
    never says which day, so "the next time that clock time comes round" is the
    only reading available.
    """
    local = now.astimezone(tzinfo)
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def parse_reset_at(text: str, *, now: datetime | None = None) -> datetime | None:
    """The UTC instant a timed limit lifts, or None if no reset time is stated."""
    match = _RESET.search(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3).lower()
    if not (1 <= hour <= 12) or minute > 59:
        return None
    hour = hour % 12 + (12 if meridiem == "p" else 0)
    return _next_occurrence(
        hour, minute, _tz(match.group(4)), now or datetime.now(timezone.utc)
    )


def parse_session_id(text: str) -> str | None:
    """Claude's own session id, when it printed one."""
    match = _SESSION_ID.search(text)
    return match.group(1) if match else None


def classify_limit(text: str, *, now: datetime | None = None) -> LimitVerdict:
    """Read implement-command output and say what kind of limit it hit."""
    if not text or not (_LIMIT_HINT.search(text) or _SPEND_HINT.search(text)):
        return LimitVerdict(NONE)
    evidence = _evidence(text)
    session_id = parse_session_id(text)
    reset_at = parse_reset_at(text, now=now)
    if reset_at is not None:
        return LimitVerdict(TIMED, reset_at, session_id, evidence)
    if _SPEND_HINT.search(text):
        return LimitVerdict(SPEND, None, session_id, evidence)
    return LimitVerdict(UNRECOGNIZED, None, session_id, evidence)


def _evidence(text: str, *, limit: int = 400) -> str:
    """The limit-ish lines, trimmed — what a person needs to see to judge."""
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if _LIMIT_HINT.search(ln) or _SPEND_HINT.search(ln)
    ]
    joined = " / ".join(lines) or text.strip()
    return joined[:limit]


def unrecognized_message(verdict: LimitVerdict) -> str:
    """What to print when Claude said "limit" in words we no longer parse."""
    return (
        "grind-session: the implement command looks rate-limited, but the "
        "message did not parse as a timed limit or a spend limit. Claude Code's "
        "output format may have changed, and waiting blindly could stall this "
        "session for hours. Stopping instead.\n"
        f"  saw: {verdict.evidence}\n"
        "  If the wording is new, please open an issue against specy-road "
        "(specy_road/claude_code_limits.py) so the parser can be updated."
    )
