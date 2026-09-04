"""PM GUI mutation fingerprint.

Two tokens are exposed:

* the **broad** token (``view_fingerprint`` on the wire), returned by
  :func:`outline_and_view_fingerprints`, which bakes in roadmap +
  planning/constitution/vision/shared +
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

from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_utils import iter_roadmap_fingerprint_files  # noqa: E402
from specy_road.bundled_scripts.roadmap_gui_lib import (  # noqa: E402
    pm_gui_mutation_fingerprint_base,
    roadmap_files_fingerprint,
)

from specy_road.registry_remote_overlay_merge import (  # noqa: E402
    roadmap_fingerprint_with_remote_refs,
)


def outline_and_view_fingerprints(repo_root: Path) -> tuple[int, int]:
    """``(narrow outline token, broad view token)`` from one walk.

    The narrow token's file set is a strict subset of the broad one's, so the
    polled endpoint that returns both used to stat the manifest and every chunk
    twice per request. The two tokens stay distinct -- that split is deliberate,
    see the module docstring -- they just share the walk now.
    """
    base = roadmap_files_fingerprint(repo_root)
    view = roadmap_fingerprint_with_remote_refs(
        repo_root, pm_gui_mutation_fingerprint_base(repo_root, base)
    )
    return base, view


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
