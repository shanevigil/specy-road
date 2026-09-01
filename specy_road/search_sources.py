"""Which files the search index watches, and how each becomes chunks.

Splitting a document is cheap; deciding *which* documents deserve indexing is
the part that determines whether search is useful. See
:mod:`specy_road.search_corpus` for why briefs and pr-bodies are largely
excluded — they are near-verbatim copies of content already indexed from its
primary source.

Every reader here is best-effort. An unparseable chunk file or an undecodable
sheet costs those chunks, never the rest of the corpus.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from specy_road.search_corpus import (
    KIND_CONSTITUTION,
    KIND_NODE,
    KIND_PLANNING,
    KIND_SHARED,
    KIND_SUMMARY,
    SCOPE_ARCHIVED,
    SCOPE_LIVE,
    Chunk,
    SourceFile,
    _MAX_BODY_CHARS,
    _rel,
    _stat,
    _SUMMARY_HEADING_STEM,
    derive_context,
)
from specy_road.text_sections import (
    normalize_heading,
    read_text_safely,
    split_sections,
)

ARCHIVE_DIR = "roadmap/archive"


def iter_source_files(root: Path) -> list[SourceFile]:
    """Every file the index watches, sorted, with its stat for change detection."""
    rels: list[str] = []
    for pattern, subdir in (
        ("*.md", "planning"),
        ("*.md", "shared"),
        ("*.md", "constitution"),
    ):
        base = root / subdir
        if base.is_dir():
            rels += [_rel(root, p) for p in sorted(base.glob(pattern))]
    rels += _work_rels(root)
    if (root / "vision.md").is_file():
        rels.append("vision.md")
    rels += _live_chunk_rels(root)
    for sub, pattern in (
        ("chunks", "*.json"),
        ("deep", "*.json"),
        ("planning", "*/*.md"),
    ):
        base = root / ARCHIVE_DIR / sub
        if base.is_dir():
            rels += [_rel(root, p) for p in sorted(base.glob(pattern))]

    seen: dict[str, SourceFile] = {}
    for rel in rels:
        if rel in seen:
            continue
        source = _stat(root, rel)
        if source is not None:
            seen[rel] = source
    return [seen[k] for k in sorted(seen)]


def _work_rels(root: Path) -> list[str]:
    """Implementation summaries, preferring the summary file over the pr-body.

    A pr-body embeds the whole summary inside `## Implementation summary`, so
    indexing both records the same prose twice in different shapes — which
    content-hash dedup cannot collapse. `finish-this-task` deletes the summary
    file on landing but always keeps the pr-body, so the pr-body is the
    *fallback* record: take it only once the summary it duplicates is gone.
    """
    work = root / "work"
    if not work.is_dir():
        return []
    out = [_rel(root, p) for p in sorted(work.glob("implementation-summary-*.md"))]
    have = {_node_id_from_work_path(rel) for rel in out}
    for path in sorted(work.glob("pr-body-*.md")):
        rel = _rel(root, path)
        if _node_id_from_work_path(rel) not in have:
            out.append(rel)
    return out


def _live_chunk_rels(root: Path) -> list[str]:
    """Chunk files named by the manifest — the live/archived boundary itself."""
    try:
        from specy_road.archive_plan import ensure_bundled_scripts_on_path

        ensure_bundled_scripts_on_path()
        from roadmap_chunk_utils import load_manifest_mapping

        includes = load_manifest_mapping(root).get("includes") or []
    except (Exception, SystemExit):
        # SystemExit for the same reason as _live_nodes: a broken manifest means
        # no node chunks, not a dead command.
        return []
    out = []
    for rel in includes:
        if isinstance(rel, str) and rel.strip():
            out.append(f"roadmap/{rel.strip()}")
    return out


def chunks_for(
    root: Path,
    rel: str,
    info: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
) -> list[Chunk]:
    """Every chunk contributed by one source file."""
    if rel.startswith(f"{ARCHIVE_DIR}/deep/"):
        return _capsule_chunks(root, rel, info, by_id)
    if rel.startswith(f"{ARCHIVE_DIR}/chunks/"):
        return _node_chunks(root, rel, info, by_id, SCOPE_ARCHIVED)
    if rel.startswith(f"{ARCHIVE_DIR}/planning/"):
        return _sheet_chunks(root, rel, info, by_id, SCOPE_ARCHIVED)
    if rel.startswith("planning/"):
        return _sheet_chunks(root, rel, info, by_id, SCOPE_LIVE)
    if rel.startswith("roadmap/"):
        return _node_chunks(root, rel, info, by_id, SCOPE_LIVE)
    if rel.startswith("work/"):
        return _summary_chunks(root, rel, info, by_id)
    kind = KIND_SHARED if rel.startswith("shared/") else KIND_CONSTITUTION
    return _doc_chunks(root, rel, kind, by_id)


def _node_key_from_path(rel: str) -> str:
    from planning_artifacts import PLANNING_FILENAME_RE

    match = PLANNING_FILENAME_RE.match(Path(rel).name)
    return match.group("uuid").lower() if match else ""


def _make(
    *,
    rel: str,
    heading: str,
    body: str,
    kind: str,
    scope: str,
    node_key: str,
    info: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
) -> Chunk | None:
    body = body.strip()[:_MAX_BODY_CHARS]
    if not body:
        return None
    identity = info.get(node_key) if node_key else None
    return Chunk(
        doc_path=rel,
        heading=heading,
        body=body,
        context=derive_context(
            identity, kind=kind, heading=heading, doc_path=rel, by_id=by_id
        ),
        node_key=node_key,
        node_id=str(identity.get("id") or "") if identity else "",
        scope=identity.get("scope", scope) if identity else scope,
        kind=kind,
    )


def _sheet_chunks(
    root: Path,
    rel: str,
    info: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    scope: str,
) -> list[Chunk]:
    from planning_artifacts import split_frontmatter

    text, ok = read_text_safely(root / rel)
    if not ok:
        return []
    _frontmatter, body = split_frontmatter(text)
    key = _node_key_from_path(rel)
    out = []
    for heading, section in split_sections(body):
        chunk = _make(
            rel=rel,
            heading=heading or "",
            body=section,
            kind=KIND_PLANNING,
            scope=scope,
            node_key=key,
            info=info,
            by_id=by_id,
        )
        if chunk:
            out.append(chunk)
    return out


def _doc_chunks(
    root: Path, rel: str, kind: str, by_id: dict[str, dict[str, Any]]
) -> list[Chunk]:
    text, ok = read_text_safely(root / rel)
    if not ok:
        return []
    out = []
    for heading, section in split_sections(text):
        chunk = _make(
            rel=rel,
            heading=heading or "",
            body=section,
            kind=kind,
            scope=SCOPE_LIVE,
            node_key="",
            info={},
            by_id=by_id,
        )
        if chunk:
            out.append(chunk)
    return out


def node_body(node: dict[str, Any]) -> str:
    """The prose a roadmap node carries, flattened for indexing."""
    lines = [str(node.get("title") or "")]
    goal = node.get("goal")
    if isinstance(goal, str) and goal.strip():
        lines += ["", goal.strip()]
    for field in ("acceptance", "risks"):
        values = node.get(field)
        if isinstance(values, list) and values:
            lines += ["", f"{field.capitalize()}:"]
            lines += [f"- {v}" for v in values if isinstance(v, str)]
    notes = node.get("notes")
    if isinstance(notes, str) and notes.strip():
        lines += ["", notes.strip()]
    return "\n".join(lines).strip()


def _nodes_in(path: Path) -> list[dict[str, Any]]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if isinstance(doc, list):
        return [n for n in doc if isinstance(n, dict)]
    if isinstance(doc, dict):
        nodes = doc.get("nodes")
        if isinstance(nodes, list):
            return [n for n in nodes if isinstance(n, dict)]
        if "id" in doc:
            return [doc]
    return []


def _node_chunks(
    root: Path,
    rel: str,
    info: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    scope: str,
) -> list[Chunk]:
    out = []
    for node in _nodes_in(root / rel):
        key = node.get("node_key")
        chunk = _make(
            rel=rel,
            heading=str(node.get("id") or ""),
            body=node_body(node),
            kind=KIND_NODE,
            scope=scope,
            node_key=key if isinstance(key, str) else "",
            info=info,
            by_id=by_id,
        )
        if chunk:
            out.append(chunk)
    return out


def _capsule_chunks(
    root: Path,
    rel: str,
    info: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
) -> list[Chunk]:
    """A deep-archive capsule: its nodes and its inlined planning-sheet bodies.

    Reachable at all because the capsule is uncompressed JSON — the deep tier
    deliberately does not gzip, so archived prose stays greppable and indexable.
    """
    try:
        capsule = json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(capsule, dict):
        return []

    out = _node_chunks(root, rel, info, by_id, SCOPE_ARCHIVED)
    for sheet in capsule.get("planning") or []:
        if not isinstance(sheet, dict):
            continue
        origin = str(sheet.get("origin") or "")
        key = _node_key_from_path(origin)
        for heading, section in split_sections(str(sheet.get("body") or "")):
            chunk = _make(
                rel=rel,
                heading=heading or "",
                body=section,
                kind=KIND_PLANNING,
                scope=SCOPE_ARCHIVED,
                node_key=key,
                info=info,
                by_id=by_id,
            )
            if chunk:
                out.append(chunk)
    return out


def _summary_chunks(
    root: Path,
    rel: str,
    info: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
) -> list[Chunk]:
    """Implementation summaries only.

    A pr-body is a brief plus a summary, and the brief half is already indexed
    from its primary sources — so only the dev-authored summary is taken.
    """
    text, ok = read_text_safely(root / rel)
    if not ok:
        return []
    node_id = _node_id_from_work_path(rel)
    key = next(
        (k for k, v in info.items() if v.get("id") == node_id and node_id), ""
    )
    whole_file = Path(rel).name.startswith("implementation-summary-")
    out = []
    for heading, section in split_sections(text):
        label = normalize_heading(heading or "")
        if not whole_file and not label.startswith(_SUMMARY_HEADING_STEM):
            continue
        chunk = _make(
            rel=rel,
            heading=heading or "",
            body=section,
            kind=KIND_SUMMARY,
            scope=SCOPE_LIVE,
            node_key=key,
            info=info,
            by_id=by_id,
        )
        if chunk:
            out.append(chunk)
    return out


def _node_id_from_work_path(rel: str) -> str:
    """``work/implementation-summary-M1.2.md`` -> ``M1.2``."""
    stem = Path(rel).stem
    for prefix in ("implementation-summary-", "pr-body-"):
        if stem.startswith(prefix):
            return stem[len(prefix):]
    return ""
