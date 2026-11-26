"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from specy_road.registration_pickup_commit import registration_commit_message

SUBJECT = registration_commit_message("thing", include_ci_skip=True)
