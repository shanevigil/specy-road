"""This clone's decisions overlay, ``roadmap/decisions.local.yaml`` (M15.22).

``decisions add --local`` writes this gitignored file instead of the tracked
``roadmap/decisions.yaml``, so a preference applies in this clone at once, with
no commit or PR on an integration branch the project protects. Readers
(``decisions list``, ``orchestrate plan``) merge it over the tracked ledger: an
entry whose id is in both is the local one, and every local entry is listed as
local. Both files take the same schema.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from specy_road.decisions import (
    DECISIONS_LOCAL_REL,
    DECISIONS_REL,
    decisions_path,
    next_decision_id,
    read_decisions,
    schema_errors,
    schema_path_for_write,
)

LOCAL = "local"
SHARED = "shared"


def _load(root: Path, *, local: bool) -> tuple[dict[str, Any], list[str]]:
    """One ledger and its problems, each naming the file; a missing file is an empty ledger."""
    rel = (DECISIONS_LOCAL_REL if local else DECISIONS_REL).as_posix()
    try:
        doc = read_decisions(decisions_path(root, local))
    except (OSError, yaml.YAMLError) as e:
        return {}, [f"{rel} could not be read ({e})"]
    errs = schema_errors(doc, schema_path_for_write(root)) if isinstance(doc, dict) else ["(root): not a mapping"]
    return (doc, []) if not errs else ({}, [f"{rel} fails its schema ({e})" for e in errs])


def merge_ledgers(shared: dict[str, Any], local: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    """``shared`` with ``local``'s entries over it by id (local wins), and the ids that came from ``local``."""
    mine = [e for e in local.get("entries") or [] if isinstance(e, dict)]
    ids = {e.get("id") for e in mine}
    kept = [e for e in shared.get("entries") or [] if not (isinstance(e, dict) and e.get("id") in ids)]
    return {"version": shared.get("version", 1), "entries": kept + mine}, ids


def load_merged(root: Path) -> tuple[dict[str, Any], set[str], list[str]]:
    """The ledger this clone reads: ``(merged doc, local ids, problems)``; with problems the doc is empty."""
    shared, errs = _load(root, local=False)
    local, local_errs = _load(root, local=True)
    if errs or local_errs:
        return {"version": 1, "entries": []}, set(), errs + local_errs
    doc, ids = merge_ledgers(shared, local)
    return doc, ids, []


def next_free_id(root: Path, prefix: str) -> str:
    """The next ``<prefix>#`` used in neither ledger, so a new entry neither shadows nor is shadowed by one."""
    both = [*(read_decisions(decisions_path(root)).get("entries") or []),
            *(read_decisions(decisions_path(root, True)).get("entries") or [])]
    return next_decision_id({"entries": both}, prefix)
