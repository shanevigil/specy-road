"""Registry claims as the orchestration state model reads them.

Its own module, importing only the registry reader, so the readiness rule
(:func:`specy_road.session_plan_git.gather_session_plan`) can take its claims from the state model
without importing the worker modules :mod:`specy_road.orchestration.state` reads, which import the
planner back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from specy_road.registry_yaml import read_registry, registry_path


def read_claims(repo_root: Path) -> dict[str, dict[str, Any]] | None:
    """Registry rows by node id (the first row per node), or ``None`` (unknown) when the file cannot
    be read or decoded, is not YAML, is not a mapping, or has an ``entries`` key whose value is not
    a list (``null``, ``false``, ``""``, ``{}`` and ``1`` included).

    An absent ``entries`` key or an empty list means no claims, as an empty registry always has. A
    row needs only a ``node_id`` to be a claim, as pickup and the readiness rule count claims.
    """
    try:
        doc = read_registry(registry_path(repo_root))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    if not isinstance(doc, dict):
        return None
    entries = doc.get("entries", [])
    if not isinstance(entries, list):
        return None
    out: dict[str, dict[str, Any]] = {}
    for e in entries:
        if isinstance(e, dict) and e.get("node_id"):
            out.setdefault(str(e["node_id"]), e)
    return out
