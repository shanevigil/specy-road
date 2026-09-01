"""In-memory search for interpreters whose SQLite lacks FTS5.

FTS5 ships in essentially every modern CPython, but it is a compile-time option
and some distribution builds omit it. Rather than fail a command over that, fall
back to scoring the same chunks in memory.

This is affordable because the corpus is small by construction: a real 48-node
project deduplicates to roughly 300 chunks over ~800 KB, so a full scan is
single-digit milliseconds. It is a genuine fallback, not a second engine — the
scoring is a plain weighted term count rather than BM25, so ranking is coarser,
but every result is still correct and correctly attributed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from specy_road.search_corpus import Chunk, build_node_info
from specy_road.search_sources import chunks_for, iter_source_files

# Mirrors the FTS5 column weights so the two paths rank in the same spirit.
_W_CONTEXT, _W_HEADING, _W_BODY = 3.0, 5.0, 1.0
_ARCHIVED_WEIGHT = 0.8
_SNIPPET_RADIUS = 90


def load_chunks(root: Path) -> list[Chunk]:
    info = build_node_info(root)
    by_id = {v["id"]: v for v in info.values() if v.get("id")}
    out: list[Chunk] = []
    for source in iter_source_files(root):
        out.extend(chunks_for(root, source.path, info, by_id))
    return out


def _terms(query: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[\w.-]+", query) if t]


def _count(haystack: str, term: str) -> int:
    return haystack.lower().count(term)


def _snippet(body: str, terms: list[str]) -> str:
    """A window around the first matching term, with the term marked."""
    low = body.lower()
    position = next(
        (low.find(t) for t in terms if low.find(t) >= 0),
        -1,
    )
    if position < 0:
        return body[:_SNIPPET_RADIUS * 2].strip()
    start = max(0, position - _SNIPPET_RADIUS)
    end = min(len(body), position + _SNIPPET_RADIUS)
    window = body[start:end].strip()
    for term in terms:
        window = re.sub(
            f"({re.escape(term)})", r"«\1»", window, flags=re.IGNORECASE
        )
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{window}{suffix}"


def search(
    root: Path,
    query: str,
    *,
    scopes: set[str] | None = None,
    kinds: set[str] | None = None,
    node_id: str | None = None,
    limit: int = 10,
    rebuild: bool = False,  # noqa: ARG001 - nothing is cached to rebuild
) -> list[dict[str, Any]]:
    terms = _terms(query)
    if not terms:
        return []
    scored: list[tuple[float, Chunk]] = []
    for chunk in load_chunks(root):
        score = 0.0
        for term in terms:
            score += _W_CONTEXT * _count(chunk.context, term)
            score += _W_HEADING * _count(chunk.heading, term)
            score += _W_BODY * _count(chunk.body, term)
        if chunk.node_id.lower() == query.strip().lower():
            score += 50.0  # the query names this node outright
        if score <= 0:
            continue
        if chunk.scope != "live":
            score *= _ARCHIVED_WEIGHT
        scored.append((score, chunk))

    scored.sort(key=lambda pair: (-pair[0], pair[1].doc_path, pair[1].heading))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, chunk in scored:
        if scopes and chunk.scope not in scopes:
            continue
        if kinds and chunk.kind not in kinds:
            continue
        if node_id and chunk.node_id != node_id:
            continue
        if chunk.content_hash in seen:
            continue
        seen.add(chunk.content_hash)
        out.append(
            {
                "score": round(score, 6),
                "doc_path": chunk.doc_path,
                "heading": chunk.heading,
                "context": chunk.context,
                "snippet": _snippet(chunk.body, terms),
                "node_id": chunk.node_id,
                "node_key": chunk.node_key,
                "scope": chunk.scope,
                "kind": chunk.kind,
            }
        )
        if len(out) >= limit:
            break
    return out
