"""Registry claims as the orchestration state model reads them.

Its own module, importing only the registry path, so the readiness rule
(:func:`specy_road.session_plan_git.gather_session_plan`) can take its claims from the state model
without importing the worker modules :mod:`specy_road.orchestration.state` reads, which import the
planner back.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from specy_road.registry_yaml import registry_path


def read_claims(repo_root: Path) -> dict[str, dict[str, Any]] | None:
    """Registry rows by node id (the first row per node), or ``None`` (unknown).

    One rule: the registry is known only when ``roadmap/registry.yaml`` is absent, or decodes as
    UTF-8 YAML whose top level is an empty document or a mapping, and that mapping's ``entries``,
    when present, is a list. Everything else is unknown: a file that cannot be read or decoded, is
    not YAML, has any other top level (``[]``, ``false``, ``0``, ``""``, a list of rows), or has an
    ``entries`` that is not a list (``null``, ``false``, ``""``, ``{}``, ``1``). An absent file, an
    empty document, an absent ``entries`` and an empty list mean no claims. The file is parsed here,
    not through ``read_registry``, which reads every falsy top level as an empty registry.

    A row needs only a ``node_id`` to be a claim, as pickup and the readiness rule count claims.
    """
    path = registry_path(repo_root)
    if not path.is_file():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    if doc is None:   # an empty document, or only comments
        return {}
    entries = doc.get("entries", []) if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        return None
    out: dict[str, dict[str, Any]] = {}
    for e in entries:
        if isinstance(e, dict) and e.get("node_id"):
            out.setdefault(str(e["node_id"]), e)
    return out
