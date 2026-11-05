"""Which specy-road version a checkout pins, and the warning when another one is running."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from specy_road import __version__
from specy_road.bundled_scripts.refresh_stubs import MANIFEST_REL
from specy_road.runtime_paths import git_root
from specy_road.specyrd_init import _load_manifest

_REQUIREMENT_PIN = re.compile(
    r"^\s*specy[-_.]road\s*(?:\[[^\]]*\])?\s*==\s*([^\s;#,]+)", re.IGNORECASE
)


def pinned_version(start: Path) -> tuple[str, str] | None:
    """``(version, where declared)`` for the specy-road this checkout pins, or None.

    A ``pin`` in ``.specyrd/manifest.json`` wins; otherwise the first
    ``specy-road==`` line in a ``requirements*.txt`` at the checkout root.
    """
    checkout = git_root(start) or start
    pin = _load_manifest(checkout).get("pin")
    if isinstance(pin, str) and pin.strip():
        return pin.strip(), str(MANIFEST_REL)
    for req in sorted(checkout.glob("requirements*.txt")):
        try:
            lines = req.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            m = _REQUIREMENT_PIN.match(line)
            if m:
                return m.group(1), req.name
    return None


def warn_if_pin_differs(start: Path) -> None:
    """One non-fatal line when the running specy-road is not the version the repo pins."""
    found = pinned_version(start)
    if found is None or found[0] == __version__:
        return
    pin, where = found
    print(
        f"specy-road: warning — this repo pins specy-road {pin} ({where}) but {__version__} "
        f"is running. If the upgrade is deliberate, update the pin; otherwise install {pin}.",
        file=sys.stderr,
    )
