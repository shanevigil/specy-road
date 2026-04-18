#!/usr/bin/env python3
"""Verify a built specy-road wheel contains the bundled PM Gantt UI.

Usage:
    python scripts/verify_wheel_contents.py <wheel.whl>

Specifically asserts that ``specy_road/pm_gantt_static/index.html`` and
at least one ``specy_road/pm_gantt_static/assets/index-*.js`` chunk are
present inside the wheel. Catches the failure mode where the npm build
step was skipped or returned an empty bundle and we'd otherwise ship a
wheel with a broken ``specy-road gui``.

Exit 0 on success, 1 with a clear message on failure.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


REQUIRED_FILES = (
    "specy_road/pm_gantt_static/index.html",
)
REQUIRED_GLOBS = (
    "specy_road/pm_gantt_static/assets/index-",  # prefix match on at least one entry
)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: verify_wheel_contents.py <wheel.whl>", file=sys.stderr)
        return 2
    wheel = Path(argv[1])
    if not wheel.is_file():
        print(f"error: wheel not found at {wheel}", file=sys.stderr)
        return 1
    with zipfile.ZipFile(wheel) as zf:
        names = set(zf.namelist())

    missing = [p for p in REQUIRED_FILES if p not in names]
    for prefix in REQUIRED_GLOBS:
        if not any(n.startswith(prefix) for n in names):
            missing.append(f"{prefix}*")
    if missing:
        print(
            "error: wheel is missing required PM Gantt UI assets:\n  "
            + "\n  ".join(missing)
            + "\n\nThis usually means the npm build step (npm run build "
              "in gui/pm-gantt/) was skipped or produced no output. Re-build "
              "the SPA and rebuild the wheel before publishing.",
            file=sys.stderr,
        )
        return 1
    print(
        f"ok: wheel {wheel.name} contains PM Gantt UI assets "
        f"(index.html + at least one index-*.js chunk)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
