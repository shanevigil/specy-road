"""Public roadmap loader: graph plus milestone full-review hold on every load."""

from __future__ import annotations

from pathlib import Path

from specy_road.roadmap_chunk_utils import discover_manifest_path
from specy_road.roadmap_graph import (
    annotate_rollup_status,
    canonical_status,
    compute_rollup_status,
    load_roadmap as _load_roadmap_graph,
    validate_roadmap_line_limits,
)
from specy_road.runtime_paths import default_user_repo_root

__all__ = [
    "annotate_rollup_status",
    "canonical_status",
    "compute_rollup_status",
    "discover_manifest_path",
    "load_roadmap",
    "validate_roadmap_line_limits",
]


def load_roadmap(root: Path | None = None) -> dict:
    """
    Return ``{version, nodes}``. ``manifest.json`` lists ``.json`` chunk paths
    under ``roadmap/`` (merged in ``includes`` order). Each node is annotated
    with computed ``rollup_status``; a milestone whose required full review is
    pending stays non-Complete there (``policy.milestone_full_review``).
    """
    root = root or default_user_repo_root()
    doc = _load_roadmap_graph(root)
    from specy_road.milestone_review_hold import demote_pending_milestone_rollups

    demote_pending_milestone_rollups(root, doc["nodes"])
    return doc
