#!/usr/bin/env python3
"""Verify a built specy-road wheel ships everything ``init project`` needs.

Usage:
    python scripts/verify_wheel_contents.py <wheel.whl> [<sdist.tar.gz> ...]

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

import importlib.util
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
    # Same for the review hand-off files: review-packet, handoff status,
    # review record, and the mark-implementation-reviewed gate read these.
    "specy_road/schemas/handoff.schema.json",
    "specy_road/schemas/review-record.schema.json",
    # Model profiles are scaffolded by `init project`; a wheel without them
    # gives adopters an empty roster guide and no `prompt` model notes.
    "specy_road/templates/project/model-profiles/README.md",
    "specy_road/templates/project/model-profiles/anthropic-claude/claude-opus-5-5.md",
)
REQUIRED_GLOBS = (
    "specy_road/pm_gantt_static/assets/index-",  # prefix match on at least one entry
)


def _hygiene():
    path = Path(__file__).resolve().parent / "check_public_hygiene.py"
    spec = importlib.util.spec_from_file_location("check_public_hygiene_wheel", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    spec.loader.exec_module(module)
    return module


def _required(wheel: Path) -> int:
    try:
        with zipfile.ZipFile(wheel) as zf:
            names = set(zf.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"error: {wheel}: {exc}", file=sys.stderr)
        return 1
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


def _denied(path: Path) -> int:
    """Denied member paths and denied text. A read failure is a non-zero exit."""
    module = _hygiene()
    root = Path(__file__).resolve().parents[1]
    hits = module.archive_promotion_hits(path, module.load_rules(root))
    if not hits:
        return 0
    print("\n".join(hits), file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: verify_wheel_contents.py <wheel.whl> [<sdist.tar.gz> ...]", file=sys.stderr)
        return 2
    failed = False
    for raw in argv[1:]:
        path = Path(raw)
        if not path.is_file():
            print(f"error: wheel not found at {path}", file=sys.stderr)
            failed = True
            continue
        if path.suffix == ".whl" and _required(path) != 0:
            failed = True
            continue
        if _denied(path) != 0:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
