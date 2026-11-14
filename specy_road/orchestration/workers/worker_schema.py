"""Schema checks for worker records and events (:mod:`worker_state`).

A leaf that adds a worker-record field writes, from its own code, records the
installed schema rejects. A worker record names the branch its leaf is built
on, so a record is valid when the installed schema or the one committed on
that ``branch`` in a specy-road checkout accepts it
(:func:`schema_revision.accepted_at_revision`). Without a branch, or outside a
checkout, only the installed schema counts.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from specy_road.runtime_paths import specy_road_package_dir
from specy_road.schema_revision import accepted_at_revision


@cache
def _validator(name: str) -> Draft202012Validator:
    path = specy_road_package_dir() / "schemas" / name
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def schema_errors(data: dict[str, Any], schema_name: str, where: Path | None = None,
                  branch: str | None = None) -> list[str]:
    """The installed schema's errors, or none when ``schema_name`` as committed on ``branch`` accepts ``data``."""
    out = []
    for e in sorted(_validator(schema_name).iter_errors(data), key=lambda e: list(e.path)):
        loc = "/".join(str(x) for x in e.path) if e.path else "(root)"
        out.append(f"{loc}: {e.message}")
    if out and where is not None and branch and accepted_at_revision(data, f"schemas/{schema_name}", where, branch):
        return []
    return out
