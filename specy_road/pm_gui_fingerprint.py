"""PM GUI mutation fingerprint.

Two tokens are exposed:

* :func:`pm_gui_mutation_fingerprint` — broad token that bakes in
  roadmap + planning/constitution/vision/shared + git HEAD + remote
  overlay. Used by ``GET /api/roadmap`` and the polling refresh hook so
  the UI can detect "something changed elsewhere" and refresh its view.

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

from roadmap_chunk_utils import iter_roadmap_fingerprint_files
from roadmap_gui_lib import pm_gui_mutation_fingerprint_base

from specy_road.registry_remote_overlay_merge import roadmap_fingerprint_with_remote_refs


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
