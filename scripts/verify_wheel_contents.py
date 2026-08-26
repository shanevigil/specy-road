#!/usr/bin/env python3
"""Verify a built specy-road wheel ships everything ``init project`` needs.

Usage:
    python scripts/verify_wheel_contents.py <wheel.whl>

Two failure modes, both invisible from an editable checkout:

* The bundled PM Gantt UI is missing because the npm build step was skipped or
  produced an empty bundle, so the wheel ships a broken ``specy-road gui``.
* A scaffold **dotfile** is missing because ``package-data`` globs use ``*``,
  which does not match a leading dot. ``init project`` copies whatever is on
  disk, so a source checkout scaffolds correctly while pip-installed users get a
  consumer repo with no ``.gitignore`` — and start committing the toolkit's own
  session artifacts.

Exit 0 on success, 1 with a clear message on failure.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


REQUIRED_FILES = (
    "specy_road/pm_gantt_static/index.html",
    # Scaffold dotfiles — see the module docstring for why these need naming.
    "specy_road/templates/project/.gitignore",
    "specy_road/templates/project/work/.gitkeep",
    # Toolkit-owned schema: the archive index validates against this copy, so a
    # wheel without it turns every archive command into a broken-install error.
    "specy_road/schemas/archive.schema.json",
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
            "error: wheel is missing required files:\n  "
            + "\n  ".join(missing)
            + "\n\nFor pm_gantt_static entries: the npm build step (npm run "
              "build in gui/pm-gantt/) was probably skipped or produced no "
              "output. Re-build the SPA and rebuild the wheel.\n"
              "For templates entries: add an explicit [tool.setuptools."
              "package-data] line for the path — glob patterns using `*` skip "
              "dotfiles.",
            file=sys.stderr,
        )
        return 1
    print(
        f"ok: wheel {wheel.name} contains the PM Gantt UI assets "
        f"and the init-project scaffold dotfiles."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
