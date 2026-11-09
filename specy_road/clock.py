"""The one place the package reads the wall clock, in UTC.

Every timestamp a record, event or lease carries comes from here, so a test
can freeze time by patching one name and every writer agrees on the shape.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """The current time as an aware UTC datetime, with microseconds."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """The current UTC time to the second, ISO 8601 with a ``+00:00`` offset."""
    return utc_now().replace(microsecond=0).isoformat()
