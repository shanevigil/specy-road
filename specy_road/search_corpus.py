"""Enumerate and chunk the text an agent should be able to search.

Two design decisions carry this module.

**The chunk unit is a markdown ``##`` section.** Planning sheets, gate sheets
and implementation summaries are all written that way, so sections are already
the semantic unit an author intended — no chunking heuristic needed, and each
lands in the "few hundred tokens" range that retrieval work converges on.

**Every chunk carries a derived context line.** Anthropic's Contextual Retrieval
prepends an LLM-written summary to each chunk before indexing because generic
prose has no structure to read; it cuts retrieval failures substantially. This
corpus does not need the LLM: every sheet already maps to a node with an id,
title, type, codename, ancestor chain and archive state, so the same context is
*derived* — free, exact, and incapable of drifting from the graph. It is indexed
as its own weighted column, which is why a search for "payments backoff" finds a
section whose body never says "payments".

What is deliberately **not** indexed: ``work/brief-*.md`` and the bulk of
``work/pr-body-*.md``. A brief inlines its ancestor planning sheets and every
``shared/*.md`` verbatim, and a pr-body re-inlines the whole brief, so the same
contract text can appear N+1 times across a repo. Indexing them would make every
query return the same passage a dozen times. Only the dev-authored
``## Implementation summary`` — the one genuinely unique record of what happened
— is taken from a pr-body.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specy_road.archive_index import iter_archived_summaries

SCOPE_LIVE = "live"
SCOPE_ARCHIVED = "archived"

KIND_PLANNING = "planning"
KIND_SHARED = "shared"
KIND_NODE = "node"
KIND_SUMMARY = "summary"
KIND_CONSTITUTION = "constitution"

# The pr-body heading is "## Implementation summary (dev-authored)"; match the
# stem so a wording tweak upstream does not silently drop the section.
_SUMMARY_HEADING_STEM = "implementation summary"

# A single pathological file must not be able to dominate the index.
_MAX_BODY_CHARS = 20_000


@dataclass(frozen=True)
class Chunk:
    """One indexable passage, with everything needed to rank and cite it."""

    doc_path: str
    heading: str
    body: str
    context: str
    node_key: str
    node_id: str
    scope: str
    kind: str

    @property
    def content_hash(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.body.encode("utf-8", "replace"))
        return digest.hexdigest()[:16]


@dataclass(frozen=True)
class SourceFile:
    """A file the index watches. ``(mtime_ns, size)`` drives incremental rebuild."""

    path: str
    mtime_ns: int
    size: int


def _stat(root: Path, rel: str) -> SourceFile | None:
    try:
        st = (root / rel).stat()
    except OSError:
        return None
    return SourceFile(path=rel, mtime_ns=st.st_mtime_ns, size=st.st_size)


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Node identity, live and archived
# ---------------------------------------------------------------------------


def build_node_info(root: Path) -> dict[str, dict[str, Any]]:
    """``{node_key: identity}`` covering both live and archived nodes.

    Archived nodes are included precisely because they are gone from the live
    graph: without them an archived planning sheet would index with no id, no
    title and no indication that the work was ever finished.
    """
    info: dict[str, dict[str, Any]] = {}
    for node in _live_nodes(root):
        key = node.get("node_key")
        if isinstance(key, str) and key:
            info[key] = {
                "id": node.get("id") or "",
                "title": node.get("title") or "",
                "type": node.get("type") or "",
                "status": node.get("rollup_status") or node.get("status") or "",
                "codename": node.get("codename") or "",
                "parent_id": node.get("parent_id") or "",
                "scope": SCOPE_LIVE,
            }
    for record, summary in _archived_summaries(root):
        key = summary.get("node_key")
        if not isinstance(key, str) or key in info:
            continue
        info[key] = {
            "id": summary.get("id") or "",
            "title": summary.get("title") or "",
            "type": summary.get("type") or "",
            "status": summary.get("status") or "Complete",
            "codename": "",
            "parent_id": "",
            "scope": SCOPE_ARCHIVED,
            "archived_at": str(record.get("archived_at") or "")[:10],
            "archive_id": record.get("archive_id") or "",
        }
    return info


def _live_nodes(root: Path) -> list[dict[str, Any]]:
    try:

        from specy_road.bundled_scripts.roadmap_load import load_roadmap

        return load_roadmap(root)["nodes"]
    except (Exception, SystemExit):
        # The roadmap loaders report a fatal problem with SystemExit rather than
        # an exception, so catching Exception alone would let a single corrupt
        # chunk file kill the whole search. Planning sheets and shared contracts
        # are still perfectly indexable without the graph.
        return []


def _archived_summaries(root: Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return iter_archived_summaries(root)


def _ancestor_titles(node_id: str, by_id: dict[str, dict[str, Any]]) -> list[str]:
    """Titles of every ancestor of ``node_id``, outermost first."""
    parts = node_id.split(".")
    out: list[str] = []
    for depth in range(1, len(parts)):
        ancestor = by_id.get(".".join(parts[:depth]))
        if ancestor:
            out.append(f"{ancestor['id']} {ancestor['title']}".strip())
    return out


def derive_context(
    identity: dict[str, Any] | None,
    *,
    kind: str,
    heading: str,
    doc_path: str,
    by_id: dict[str, dict[str, Any]],
) -> str:
    """The context line indexed alongside a chunk.

    This is the LLM-free stand-in for Contextual Retrieval's generated prefix:
    everything it would have had to infer is already recorded in the graph.
    """
    bits: list[str] = []
    if identity:
        head = f"{identity['id']} {identity['title']}".strip()
        bits.append(head)
        for extra in (identity.get("type"), identity.get("status")):
            if extra:
                bits.append(str(extra))
        if identity.get("codename"):
            bits.append(str(identity["codename"]))
        chain = _ancestor_titles(str(identity.get("id") or ""), by_id)
        if chain:
            bits.append("under " + " / ".join(chain))
        if identity.get("scope") == SCOPE_ARCHIVED:
            when = identity.get("archived_at") or ""
            bits.append(f"archived {when}".strip())
    else:
        bits.append(doc_path)
    bits.append(_KIND_LABELS.get(kind, kind))
    # A node chunk's heading is its id, which the head already states.
    if heading and kind != KIND_NODE:
        bits.append(heading)
    return " · ".join(b for b in bits if b)


_KIND_LABELS = {
    KIND_PLANNING: "planning sheet",
    KIND_SHARED: "shared contract",
    KIND_NODE: "roadmap node",
    KIND_SUMMARY: "implementation summary",
    KIND_CONSTITUTION: "governance",
}
