"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from specy_road.runtime_paths import specy_road_package_dir

SKILL = specy_road_package_dir() / "templates" / "specyrd" / "commands" / "specyrd-orchestrate.md"
