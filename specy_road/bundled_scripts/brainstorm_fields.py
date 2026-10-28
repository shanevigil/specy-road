"""The v2 idea fields: provenance, evidence records, clusters, critics, decisions.

Kept beside :mod:`brainstorm_session` so the session module stays readable.
Every field here is optional and omitted from the YAML when empty: the
session file is Git-tracked and edited by hand, and a 30-idea file with nine
empty keys per idea is unreadable. ``evidence`` stays the plain URL list the
GUI and promote already use; the structured records live in ``sources``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # the real import would be circular; raised lazily below
    from specy_road.bundled_scripts.brainstorm_session import BrainstormError

VERIFICATIONS = ("unverified", "retrieved", "not-found", "blocked")
STANCES = ("for", "against")
OVERLAP_RELATIONS = ("same-problem-same-solution", "same-problem-different-solution",
                     "prerequisite", "superseded", "adjacent")
ORIGIN_KEYS = ("harness", "model", "lens", "round", "shard")

EXTRA_DEFAULTS: dict[str, Any] = {
    "origin": None, "cluster_id": None, "sources": [], "overlap": [], "critic": None,
    "hypothesis": "", "assumptions": [], "decision": None, "verdict_why": "",
}


def _bad(ident: str, msg: str) -> "BrainstormError":
    return _error(f"idea {ident}: {msg}")


def parse_origin(text: str | None) -> dict[str, str] | None:
    """``harness/model/lens/round[/shard]`` → mapping; ``None`` for nothing."""
    if not text or not text.strip():
        return None
    parts = [p.strip() for p in text.split("/")]
    return {k: v for k, v in zip(ORIGIN_KEYS, parts) if v}


def _error(msg: str) -> "BrainstormError":
    from specy_road.bundled_scripts.brainstorm_session import BrainstormError

    return BrainstormError(msg)


def parse_overlap(text: str) -> dict[str, str]:
    """``NODE_ID:relation`` → mapping, both parts validated.

    Checked here, at the CLI boundary: an empty node id written to the file
    would only surface on the next read, which rejects the whole session.
    """
    node, _, rel = text.partition(":")
    node = node.strip()
    rel = rel.strip() or "adjacent"
    if not node:
        raise _error(f"--overlap {text!r}: expected NODE_ID:RELATION with a node id")
    if rel not in OVERLAP_RELATIONS:
        raise _error(f"overlap relation {rel!r} not one of {', '.join(OVERLAP_RELATIONS)}")
    return {"node_id": node, "relation": rel}


def source_record(url: str, *, quote: str = "", supports: str = "", stance: str = "for",
                  tool: str = "", source_type: str = "", retrieved_at: str = "",
                  verification: str = "unverified") -> dict[str, Any]:
    if not (url or "").strip():
        raise _error("--url is required: a source without a URL cannot be verified")
    if stance not in STANCES:
        raise _error(f"stance {stance!r} not one of {', '.join(STANCES)}")
    rec = {"url": url.strip(), "quote": quote.strip(), "supports": supports.strip(), "stance": stance,
           "tool": tool.strip(), "source_type": source_type.strip(), "retrieved_at": retrieved_at.strip(),
           "verification": verification}
    return {k: v for k, v in rec.items() if v not in ("", None)}


def parse_extra(raw: dict[str, Any], ident: str) -> dict[str, Any]:  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
    """The v2 fields from a loaded idea mapping, validated, defaults filled."""
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in EXTRA_DEFAULTS.items()}
    origin = raw.get("origin")
    if isinstance(origin, dict):
        out["origin"] = {str(k): str(v) for k, v in origin.items() if str(k) in ORIGIN_KEYS}
    elif isinstance(origin, str):
        out["origin"] = parse_origin(origin)
    cluster = raw.get("cluster_id")
    if isinstance(cluster, str) and cluster.strip():
        out["cluster_id"] = cluster.strip()
    sources = raw.get("sources")
    if isinstance(sources, list):
        for s in sources:
            if not isinstance(s, dict) or not str(s.get("url", "")).strip():
                raise _bad(ident, "each source needs a url")
            v = s.get("verification", "unverified")
            if v not in VERIFICATIONS:
                raise _bad(ident, f"verification {v!r} not one of {', '.join(VERIFICATIONS)}")
            stance = s.get("stance", "for")
            if stance not in STANCES:
                raise _bad(ident, f"stance {stance!r} not one of {', '.join(STANCES)}")
            out["sources"].append({k: v for k, v in s.items() if v not in ("", None)})
    overlap = raw.get("overlap")
    if isinstance(overlap, list):
        for o in overlap:
            if not isinstance(o, dict) or not o.get("node_id"):
                raise _bad(ident, "each overlap needs a node_id")
            if o.get("relation", "adjacent") not in OVERLAP_RELATIONS:
                raise _bad(ident, f"overlap relation {o.get('relation')!r} unknown")
            out["overlap"].append({"node_id": str(o["node_id"]), "relation": str(o.get("relation", "adjacent"))})
    if isinstance(raw.get("critic"), dict):
        out["critic"] = {str(k): str(v) for k, v in raw["critic"].items()}
    if isinstance(raw.get("hypothesis"), str):
        out["hypothesis"] = raw["hypothesis"].strip()
    if isinstance(raw.get("verdict_why"), str):
        out["verdict_why"] = raw["verdict_why"].strip()
    if isinstance(raw.get("assumptions"), list):
        out["assumptions"] = [str(a).strip() for a in raw["assumptions"] if str(a).strip()]
    if isinstance(raw.get("decision"), dict):
        out["decision"] = {str(k): str(v) for k, v in raw["decision"].items() if v not in ("", None)}
    return out


def extra_to_dict(idea: Any) -> dict[str, Any]:
    """Only the v2 fields that carry something, for a legible session file."""
    out: dict[str, Any] = {}
    for key, default in EXTRA_DEFAULTS.items():
        value = getattr(idea, key, default)
        if value not in (None, "", []):
            out[key] = value
    return out
