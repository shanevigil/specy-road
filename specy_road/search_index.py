"""The search index: SQLite FTS5 with BM25, built from the roadmap corpus.

**No embeddings, deliberately.** Anthropic replaced Claude Code's early
RAG-plus-vector-store with agentic search because lexical retrieval over a live
filesystem avoids the staleness, privacy and operational failure modes a vector
index brings — and a roadmap corpus changes on every commit, which is exactly
where stale embeddings hurt most. The identifiers people actually search for
here (``M1.2``, ``retry-queue``, a ``node_key`` UUID) are also precisely what
lexical matching is best at and embeddings are worst at.

Ranking fuses two ranked lists with Reciprocal Rank Fusion (``1/(k+rank)``,
k=60), which needs no score normalisation between them:

* **BM25** over the chunk text, weighting the derived context and the heading
  above the body.
* **Structural** matches — the query naming a node id, codename or node_key
  outright. This is why ``specy-road search M1.2`` works as well as a prose
  query without a special code path.

The index lives beside the history cache under ``.specyrd/cache/`` and inherits
its contract exactly: gitignored, disposable, ``INDEX_VERSION``-or-discard with
no migration path ever written, and silent on every failure — a read-only
checkout costs a rebuild, never a command.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from specy_road.history_cache import CACHE_DIR
from specy_road.search_corpus import Chunk, build_node_info
from specy_road.search_sources import chunks_for, iter_source_files

INDEX_VERSION = 1
INDEX_FILENAME = "search-index.sqlite3"

# BM25 column weights: the derived context and the heading are short and
# high-signal, so a hit there outranks the same term buried in a long body.
_W_CONTEXT, _W_HEADING, _W_BODY = 3.0, 5.0, 1.0

_RRF_K = 60
_CANDIDATES = 200

# Guillemets, not asterisks: the corpus is markdown and ** already means bold,
# so asterisk markers nest inside emphasised text and render as noise.
_HL_OPEN, _HL_CLOSE = "«", "»"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS docs (
  path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL, size INTEGER NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
  context, heading, body,
  doc_path UNINDEXED, node_key UNINDEXED, node_id UNINDEXED,
  scope UNINDEXED, kind UNINDEXED, content_hash UNINDEXED,
  tokenize='porter unicode61');
"""


def index_path(root: Path) -> Path:
    return root / CACHE_DIR / INDEX_FILENAME


def fts5_available() -> bool:
    """Whether this interpreter's SQLite was built with FTS5."""
    try:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        con.close()
    except sqlite3.Error:
        return False
    return True


def _open(path: Path) -> sqlite3.Connection | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        con.executescript(_SCHEMA)
    except (OSError, sqlite3.Error):
        return None
    return con


def _connect(root: Path) -> sqlite3.Connection | None:
    """Open the index, discarding it if it is corrupt or from another version.

    Both failures take the same path on purpose: the index is derived, so
    throwing it away and re-deriving is always correct and always cheaper than
    reasoning about what a half-usable index might contain. This is why no
    migration for it will ever need to be written.
    """
    path = index_path(root)
    con = _open(path)
    if con is not None and _stored_version(con) == INDEX_VERSION:
        return con
    if con is not None:
        con.close()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return None
    con = _open(path)
    if con is None:
        return None
    try:
        con.execute(
            "INSERT OR REPLACE INTO meta VALUES ('version', ?)", (str(INDEX_VERSION),)
        )
        con.commit()
    except sqlite3.Error:
        return None
    return con


def _stored_version(con: sqlite3.Connection) -> int:
    try:
        row = con.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        return int(row["value"]) if row is not None else -1
    except (sqlite3.Error, TypeError, ValueError):
        return -1


def refresh(root: Path, *, rebuild: bool = False) -> sqlite3.Connection | None:
    """Bring the index up to date with the working tree, incrementally.

    Only files whose ``(mtime_ns, size)`` changed are re-chunked, so an edit to
    one planning sheet costs one file's work rather than a full rebuild. This is
    working-tree-accurate on purpose: unlike the history index, search must
    reflect uncommitted edits.
    """
    if rebuild:
        try:
            index_path(root).unlink(missing_ok=True)
        except OSError:
            pass
    con = _connect(root)
    if con is None:
        return None

    sources = iter_source_files(root)
    current = {s.path: s for s in sources}
    try:
        known = {
            r["path"]: (r["mtime_ns"], r["size"])
            for r in con.execute("SELECT path, mtime_ns, size FROM docs")
        }
    except sqlite3.Error:
        known = {}

    stale = [p for p, s in current.items() if known.get(p) != (s.mtime_ns, s.size)]
    gone = [p for p in known if p not in current]
    if not stale and not gone:
        return con

    info = build_node_info(root)
    by_id = {v["id"]: v for v in info.values() if v.get("id")}
    try:
        for path in [*stale, *gone]:
            con.execute("DELETE FROM chunks WHERE doc_path = ?", (path,))
            con.execute("DELETE FROM docs WHERE path = ?", (path,))
        for path in stale:
            for chunk in chunks_for(root, path, info, by_id):
                _insert(con, chunk)
            source = current[path]
            con.execute(
                "INSERT OR REPLACE INTO docs VALUES (?, ?, ?)",
                (source.path, source.mtime_ns, source.size),
            )
        con.commit()
    except sqlite3.Error:
        return con
    return con


def _insert(con: sqlite3.Connection, chunk: Chunk) -> None:
    con.execute(
        "INSERT INTO chunks (context, heading, body, doc_path, node_key,"
        " node_id, scope, kind, content_hash) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            chunk.context,
            chunk.heading,
            chunk.body,
            chunk.doc_path,
            chunk.node_key,
            chunk.node_id,
            chunk.scope,
            chunk.kind,
            chunk.content_hash,
        ),
    )


def _match_expression(query: str, *, conjunctive: bool) -> str:
    """A user query as safe FTS5 syntax.

    Every term is quoted, so punctuation an operator-happy parser would choke on
    — ``M1.2``, a UUID, a hyphenated codename — is matched literally.
    """
    terms = [t for t in query.replace('"', " ").split() if t.strip()]
    if not terms:
        return ""
    joiner = " AND " if conjunctive else " OR "
    return joiner.join(f'"{t}"' for t in terms)


def _bm25_rows(
    con: sqlite3.Connection, query: str, limit: int
) -> list[sqlite3.Row]:
    """Ranked rows, tried strict (AND) first then permissive (OR).

    A precise multi-term query should not be diluted by unrelated single-term
    hits, but a query where one term simply is not present should still answer.
    """
    for conjunctive in (True, False):
        expression = _match_expression(query, conjunctive=conjunctive)
        if not expression:
            return []
        try:
            rows = con.execute(
                "SELECT *, snippet(chunks, 2, '«', '»', '…', 20) AS snip,"
                " bm25(chunks, ?, ?, ?) AS score FROM chunks"
                " WHERE chunks MATCH ? ORDER BY score LIMIT ?",
                (_W_CONTEXT, _W_HEADING, _W_BODY, expression, limit),
            ).fetchall()
        except sqlite3.Error:
            return []
        if rows:
            return rows
    return []


def _structural_rows(con: sqlite3.Connection, query: str) -> list[sqlite3.Row]:
    """Rows the query names outright: a node id, a node_key, or a codename."""
    token = query.strip()
    if not token or " " in token:
        return []
    try:
        return con.execute(
            "SELECT *, '' AS snip, 0.0 AS score FROM chunks"
            " WHERE node_id = ? COLLATE NOCASE OR node_key = ? COLLATE NOCASE"
            " ORDER BY doc_path, heading LIMIT ?",
            (token, token.lower(), _CANDIDATES),
        ).fetchall()
    except sqlite3.Error:
        return []


# Archived matches are demoted, not hidden. A live sheet and the archived sheet
# it superseded often both match; the current one should win. But an archived
# hit is still a real decision — frequently the *final* one — so the penalty is
# mild rather than a hard sort key that would bury archived-only answers.
_ARCHIVED_WEIGHT = 0.8


def _row_key(row: Any) -> str:
    return f"{row['doc_path']}\0{row['heading']}\0{row['content_hash']}"


def _fuse(ranked_lists: list[list[Any]]) -> list[tuple[float, Any]]:
    """Reciprocal Rank Fusion over the input rankings.

    RRF needs no score normalisation between lists, which is what lets a BM25
    score and a boolean structural match be combined without inventing a
    conversion between them.
    """
    scores: dict[str, float] = {}
    rows: dict[str, Any] = {}
    for ranked in ranked_lists:
        for rank, row in enumerate(ranked):
            key = _row_key(row)
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + rank + 1)
            rows.setdefault(key, row)
    fused = []
    for key, row in rows.items():
        score = scores[key]
        if row["scope"] != "live":
            score *= _ARCHIVED_WEIGHT
        fused.append((score, row))
    fused.sort(key=lambda pair: (-pair[0], pair[1]["doc_path"], pair[1]["heading"]))
    return fused


def _as_result(score: float, row: Any) -> dict[str, Any]:
    return {
        "score": round(score, 6),
        "doc_path": row["doc_path"],
        "heading": row["heading"],
        "context": row["context"],
        "snippet": (row["snip"] or "").strip() or row["body"][:200].strip(),
        "node_id": row["node_id"],
        "node_key": row["node_key"],
        "scope": row["scope"],
        "kind": row["kind"],
    }


def search(
    root: Path,
    query: str,
    *,
    scopes: set[str] | None = None,
    kinds: set[str] | None = None,
    node_id: str | None = None,
    limit: int = 10,
    rebuild: bool = False,
) -> list[dict[str, Any]]:
    """Ranked results for ``query``, newest index state, best match first.

    Duplicate passages are collapsed by content hash: the corpus still contains
    some genuine repetition (an archived sheet identical to the live one it was
    copied from), and returning the same text twice wastes the context this
    whole feature exists to protect.
    """
    if not fts5_available():
        from specy_road import search_fallback

        return search_fallback.search(
            root,
            query,
            scopes=scopes,
            kinds=kinds,
            node_id=node_id,
            limit=limit,
        )
    con = refresh(root, rebuild=rebuild)
    if con is None:
        return []
    fused = _fuse(
        [_bm25_rows(con, query, _CANDIDATES), _structural_rows(con, query)]
    )

    out: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for score, row in fused:
        if scopes and row["scope"] not in scopes:
            continue
        if kinds and row["kind"] not in kinds:
            continue
        if node_id and row["node_id"] != node_id:
            continue
        digest = row["content_hash"]
        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        out.append(_as_result(score, row))
        if len(out) >= limit:
            break
    return out


def corpus_stats(root: Path) -> dict[str, int]:
    """Document and chunk counts, for `--json` callers and diagnostics."""
    con = refresh(root)
    if con is None:
        return {"documents": 0, "chunks": 0}
    try:
        docs = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        chunks = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    except sqlite3.Error:
        return {"documents": 0, "chunks": 0}
    return {"documents": int(docs), "chunks": int(chunks)}
