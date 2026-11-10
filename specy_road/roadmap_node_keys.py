"""Stable node_key (UUID) helpers for roadmap nodes."""

from __future__ import annotations

import re
import uuid

# RFC 4122 UUID lowercase hex (versions 1–8). Repo uses uuid4 for new keys and
# uuid5 for deterministic migrated keys; dependency patches must accept both.
NODE_KEY_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
)


def new_node_key() -> str:
    return str(uuid.uuid4())


def build_key_to_node(nodes: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for n in nodes:
        k = n.get("node_key")
        if isinstance(k, str) and k:
            out[k] = n
    return out
