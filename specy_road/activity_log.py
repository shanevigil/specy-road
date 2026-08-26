"""When each node was last worked on: ``roadmap/activity.json``.

A sidecar keyed by ``node_key``, not fields on the nodes themselves. Two
reasons, both load-bearing:

* ``<repo_root>/schemas/roadmap.schema.json`` is **consumer-owned** and uses
  ``additionalProperties: false``. A new node field would fail every adopter's
  ``validate`` until they hand-edited that file.
* Activity changes on every pickup, review and finish. Writing it into chunks
  would churn the roadmap diffs that land in each PR, for data nobody reviews.

Every write is best-effort. Recording activity must never be the reason a
pickup or a finish fails, so :func:`record_activity` swallows its own errors.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specy_road.runtime_paths import specy_road_package_dir

ACTIVITY_VERSION = 1
ACTIVITY_FILENAME = "activity.json"

KIND_PICKED_UP = "picked_up"
KIND_REVIEWED = "reviewed"
KIND_FINISHED = "finished"
KIND_EDITED = "edited"
KIND_BACKFILLED = "backfilled"


def activity_path(root: Path) -> Path:
    return (root / "roadmap" / ACTIVITY_FILENAME).resolve()


def empty_activity() -> dict[str, Any]:
    return {"version": ACTIVITY_VERSION, "nodes": {}}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def bundled_activity_schema() -> dict[str, Any]:
    path = specy_road_package_dir() / "schemas" / "activity.schema.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"missing bundled activity schema at {path} (broken install)."
        )
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate_activity(doc: dict[str, Any]) -> None:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(bundled_activity_schema())
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        loc = "/".join(str(p) for p in first.path) or "."
        raise ValueError(f"activity log invalid at {loc}: {first.message}")


def load_activity(root: Path) -> dict[str, Any]:
    """Load the log, or an empty one.

    Unlike the archive index, a malformed activity log is **not** fatal: it is
    display metadata, and refusing to run `finish-this-task` because a
    cosmetic timestamp file got mangled would be a bad trade. Callers that
    care can validate explicitly.
    """
    path = activity_path(root)
    if not path.is_file():
        return empty_activity()
    try:
        with path.open(encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return empty_activity()
    if not isinstance(doc, dict) or not isinstance(doc.get("nodes"), dict):
        return empty_activity()
    return doc


def write_activity(root: Path, doc: dict[str, Any]) -> Path:
    validate_activity(doc)
    path = activity_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(body + ("" if body.endswith("\n") else "\n"), encoding="utf-8")
    return path


def set_activity(
    doc: dict[str, Any], node_key: str, kind: str, at: str | None = None
) -> dict[str, Any]:
    """Record activity in ``doc`` in place, keeping the **latest** timestamp.

    Out-of-order writes happen: a backfill can run after live activity was
    already recorded, and grind sessions interleave. Taking the max keeps the
    column honest rather than letting a stale write win.
    """
    stamp = at or utc_now_iso()
    nodes = doc.setdefault("nodes", {})
    existing = nodes.get(node_key)
    if isinstance(existing, dict) and isinstance(existing.get("at"), str):
        if existing["at"] >= stamp:
            return doc
    nodes[node_key] = {"at": stamp, "kind": kind}
    return doc


def record_activity(
    root: Path, node_key: str | None, kind: str, at: str | None = None
) -> None:
    """Best-effort record of one activity. Never raises.

    Called from pickup, review, finish and edit paths — none of which should
    fail because a display-only sidecar could not be written (read-only
    checkout, races, a mangled file).
    """
    if not isinstance(node_key, str) or not node_key:
        return
    try:
        write_activity(root, set_activity(load_activity(root), node_key, kind, at))
    except Exception:  # noqa: BLE001 - deliberately non-fatal, see docstring
        pass


def record_activity_for_node_id(
    root: Path, node_id: str, kind: str, at: str | None = None
) -> None:
    """Same, for callers that hold a display id rather than a ``node_key``."""
    try:
        from roadmap_load import load_roadmap

        for n in load_roadmap(root)["nodes"]:
            if n.get("id") == node_id:
                record_activity(root, n.get("node_key"), kind, at)
                return
    except Exception:  # noqa: BLE001 - see record_activity
        pass


def activity_by_node_key(root: Path) -> dict[str, dict[str, Any]]:
    """``{node_key: {at, kind}}`` for the PM GUI payload."""
    nodes = load_activity(root).get("nodes")
    if not isinstance(nodes, dict):
        return {}
    return {
        k: v
        for k, v in nodes.items()
        if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("at"), str)
    }
