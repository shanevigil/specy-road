"""PM GUI mutation fingerprint.

Two tokens are exposed:

* :func:`pm_gui_mutation_fingerprint` — broad token (``view_fingerprint`` on
  the wire) that bakes in roadmap + planning/constitution/vision/shared +
  ``git HEAD`` + remote overlay ref tips. The PM GUI **polling refresh** hook
  compares this value to detect "something changed" (including after a
  **deferred** ``git fetch`` completed). It is **not** sent on mutating
  requests; the **narrow** outline token is used for optimistic concurrency
  there.

* :func:`outline_mutation_fingerprint` — **narrow** token that only
  includes files whose change actually affects whether an outline /
  node mutation is safe to apply: ``roadmap/manifest.json``, every
  included chunk file under ``roadmap/``, and ``roadmap/registry.yaml``.
  This is what the mutating routes guard against. A PM dragging M9.2
  must not be blocked because Cursor autosaved a planning sheet, an
  IDE bumped ``shared/notes.md``, ``git fetch`` updated a remote ref,
  or any other in-flight noise happens to touch a file the broad
  fingerprint watches.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ``roadmap_chunk_utils`` and ``roadmap_gui_lib`` live under
# ``specy_road/bundled_scripts/`` and are imported via plain module
# names. ``gui_app.py`` adds that directory to ``sys.path`` at server
# startup, but if this module is imported standalone (e.g. by a one-off
# diagnostic ``python -c`` or by tests that don't go through the FastAPI
# app) the path bootstrap hasn't run yet. Add the directory here so the
# module imports cleanly in any context.
_BUNDLED = Path(__file__).resolve().parent / "bundled_scripts"
if str(_BUNDLED) not in sys.path:
    sys.path.insert(0, str(_BUNDLED))

from roadmap_chunk_utils import iter_roadmap_fingerprint_files  # noqa: E402
from roadmap_gui_lib import pm_gui_mutation_fingerprint_base  # noqa: E402

from specy_road.registry_remote_overlay_merge import (  # noqa: E402
    roadmap_fingerprint_with_remote_refs,
)


def pm_gui_mutation_fingerprint(repo_root: Path) -> int:
    """Broad token for view-refresh signalling.

    Includes roadmap + planning/constitution/vision/shared + git HEAD +
    (optionally) remote overlay refs. NOT used directly by the mutation
    guard — see :func:`outline_mutation_fingerprint`.
    """
    base = pm_gui_mutation_fingerprint_base(repo_root)
    return roadmap_fingerprint_with_remote_refs(repo_root, base)


def outline_mutation_fingerprint(repo_root: Path) -> int:
    """Narrow token used to guard mutating PM API routes.

    Only files whose change can actually invalidate an outline / node
    write are included: the manifest, every roadmap chunk it lists, and
    the registry. Noise from planning autosave, IDE indexing, remote
    fetches, or HEAD movement does not shift this token, so legitimate
    PM edits are not rejected by races outside the user's control.
    """
    h = 0
    for p in iter_roadmap_fingerprint_files(repo_root):
        try:
            h += p.stat().st_mtime_ns
        except OSError:
            continue
    return h
