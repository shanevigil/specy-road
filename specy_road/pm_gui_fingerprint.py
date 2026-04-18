"""PM GUI mutation fingerprint: roadmap + planning/constitution/vision/shared + remote overlay."""

from __future__ import annotations

from pathlib import Path

from roadmap_gui_lib import pm_gui_mutation_fingerprint_base

from specy_road.registry_remote_overlay_merge import roadmap_fingerprint_with_remote_refs


def pm_gui_mutation_fingerprint(repo_root: Path) -> int:
    """Single token for GET /api/roadmap and GET /api/roadmap/fingerprint (optimistic concurrency)."""
    base = pm_gui_mutation_fingerprint_base(repo_root)
    return roadmap_fingerprint_with_remote_refs(repo_root, base)
