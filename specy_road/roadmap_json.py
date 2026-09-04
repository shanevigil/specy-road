"""How roadmap JSON is written, and what shapes are accepted when reading it.

Both halves were duplicated, and both are load-bearing.

**Writing.** Four modules rendered "canonical" JSON with their own copy of the
same ``json.dumps`` call, and one of them had already lost ``ensure_ascii=False``
— so a node titled in Japanese was escaped in a deep archive's reference file
and left as UTF-8 in the capsule beside it. These bytes are compared by humans
in diffs and hashed by :mod:`specy_road.archive_deep`, which is exactly why
there can only be one renderer.

**Reading.** A chunk may be a bare list, a ``{"nodes": [...]}`` object, or a
single node object. Four readers branched on those three shapes independently,
two of them noting in their own docstrings that they were copies.

This lives in the library rather than in ``bundled_scripts/roadmap_chunk_utils``
so that the archive, history and search modules can import it directly instead
of each arranging for the scripts directory to be importable first.
"""

from __future__ import annotations

import json
from typing import Any


def render_canonical_json(doc: object) -> str:
    """Canonical JSON text: stable key order, indent 2, UTF-8, trailing newline."""
    body = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False)
    return body if body.endswith("\n") else body + "\n"


def nodes_from_chunk_doc(doc: object) -> list[dict[str, Any]] | None:
    """Nodes out of a parsed chunk document, or ``None`` if it is not one.

    Shape-reading only. Whether an unrecognised document is fatal is the
    caller's decision: the loader fails the run, while the history walk, the
    search corpus and the at-ref reader skip the file.
    """
    if isinstance(doc, list):
        return [n for n in doc if isinstance(n, dict)]
    if isinstance(doc, dict):
        nodes = doc.get("nodes")
        if isinstance(nodes, list):
            return [n for n in nodes if isinstance(n, dict)]
        if "id" in doc:
            return [doc]
    return None
