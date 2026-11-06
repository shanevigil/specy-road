"""Whether a roster entry's harness gets a fixed model id or routes dynamically (M11.33, M15.31).

Imports from :mod:`specy_road.orchestration_config` are local to each function so this module can load before
``orchestration_config`` finishes re-exporting it (no import cycle).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def entry_launch_model(repo_root: Path, entry: dict[str, Any]) -> str | None:
    """The model id ``review delegate`` passes the harness, or ``None`` when the harness would use its default."""
    from specy_road.orchestration_config import harness_model  # noqa: PLC0415 — break cycle with config re-export
    from specy_road.orchestration_pinned import pinned_profile_for_entry  # noqa: PLC0415 — it imports orchestration_config

    prof = pinned_profile_for_entry(repo_root, entry)
    prof_api = prof.api_id if prof is not None and prof.ok else None
    if entry.get("harness") == "cursor":
        cli = (entry.get("channels") or {}).get("cli")
        if cli:
            from specy_road.worker_models import command_model  # noqa: PLC0415 — worker modules load late

            return command_model(cli)
        return harness_model(entry, prof_api or "")
    if prof_api is not None:
        return harness_model(entry, prof_api)
    return harness_model(entry)


def entry_routing(repo_root: Path, entry: dict[str, Any]) -> str:
    """``dynamic`` when the entry declares ``routing: dynamic``, or no model would be passed (any harness), or a
    ``cursor`` entry is told ``auto``. Else ``fixed``."""
    if entry.get("routing") == "dynamic":
        return "dynamic"
    model = entry_launch_model(repo_root, entry)
    if model is None:
        return "dynamic"
    if entry.get("harness") == "cursor" and model.strip().lower() == "auto":
        return "dynamic"
    return "fixed"


def routing_problem(repo_root: Path, config: dict[str, Any], data: dict[str, Any]) -> str | None:
    """Why an approval does not count under ``reviewers_distinct_families``: its entry's harness routes models
    dynamically (:func:`entry_routing`) and the entry is not ``pinned``, so the family behind it is not known."""
    from specy_road.orchestration_config import roster_entry  # noqa: PLC0415 — break cycle with config re-export

    entry = roster_entry(config, data["model"]) or {}
    if (data.get("verdict") != "approve" or not config["policy"].get("reviewers_distinct_families")
            or entry.get("pinned") or entry_routing(repo_root, entry) == "fixed"):
        return None
    if entry_launch_model(repo_root, entry) is None:
        harness = entry.get("harness") or "generic"
        return (f"{data['model']!r}: no model is passed to {harness}; set harness_model on the roster entry, or "
                "pinned: true once the maintainer has checked the harness honours the requested model; it counts "
                "toward distinct families only once pinned")
    return (f"{data['model']!r} runs on a harness that routes models dynamically (routing: dynamic, or cursor with "
            "no model or auto), so its family is not known; it counts toward distinct families only once its roster "
            "entry sets pinned: true")
