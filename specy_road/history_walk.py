"""Replay the roadmap over git history and emit events.

The walk reconstructs the merged graph at each mainline commit that touched it,
diffs consecutive reconstructions, and records what changed. Three sources feed
it, in descending order of cost:

* **The graph** — ``roadmap/manifest.json`` plus the chunks its ``includes``
  names. Rebuilt only on commits that actually changed one of those blobs.
* **The archive ledger** — ``roadmap/archive/index.json``. Diffed on commits
  that changed it, and used to reconcile away the ``removed``/``created`` events
  archiving and restoring would otherwise manufacture.
* **Planning sheets** — free. The flat-``planning/`` naming rule puts the
  ``node_key`` in the filename, so a sheet edit is attributed from the path
  alone, with no blob read at all, and it survives the renames that renumbering
  and recodenaming cause.

Best-effort throughout: a directory that is not a git worktree, a missing git
binary or a shallow clone yields fewer events, never an exception.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from specy_road.history_events import (
    SHEET_EDIT,
    archive_events,
    diff_snapshots,
    make_event,
    reconcile_archive,
    snapshot,
)
from specy_road.history_git import (
    COMMIT_MARK,
    FIELD_SEP,
    BlobReader,
    log_raw,
    ls_tree_blobs,
)
from specy_road.runtime_paths import project_prefix, rebase_to_project
from specy_road.roadmap_json import nodes_from_chunk_doc

MANIFEST_REL = "roadmap/manifest.json"
ARCHIVE_INDEX_REL = "roadmap/archive/index.json"
ARCHIVE_PREFIX = "roadmap/archive/"
ROADMAP_PREFIX = "roadmap/"
PLANNING_PREFIX = "planning/"
SCOPES = ["roadmap", "planning"]


@dataclass
class Commit:
    """One mainline commit and the roadmap files it changed."""

    sha: str
    at: str
    author: str
    # (project-relative path, new blob sha) — blob is None for a deletion.
    changes: list[tuple[str, str | None]] = field(default_factory=list)

    def meta(self) -> dict[str, Any]:
        return {"commit": self.sha, "at": self.at, "author": self.author}


def parse_log(text: str, prefix: str = "") -> list[Commit]:
    """Parse ``git log --raw --no-abbrev`` output into commits, oldest first."""
    commits: list[Commit] = []
    current: Commit | None = None
    for line in text.splitlines():
        if line.startswith(COMMIT_MARK):
            parts = (line[1:].split(FIELD_SEP) + ["", ""])[:3]
            current = Commit(sha=parts[0], at=parts[1], author=parts[2])
            commits.append(current)
            continue
        if current is None or not line.startswith(":"):
            continue
        meta, _, path = line.partition("\t")
        fields = meta.split()
        # ":<srcmode> <dstmode> <srcsha> <dstsha> <status>"
        if len(fields) < 5 or not path:
            continue
        rel = rebase_to_project(path, prefix)
        if rel is None:
            continue
        deleted = fields[4].startswith("D")
        current.changes.append((rel, None if deleted else fields[3]))
    return commits


def _include_path(rel: str) -> str | None:
    """A manifest include as a project-relative path, or ``None`` if it escapes."""
    joined = posixpath.normpath(posixpath.join(ROADMAP_PREFIX, rel))
    return joined if joined.startswith(ROADMAP_PREFIX) else None




def build_graph(
    reader: BlobReader, state: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """The merged graph snapshot implied by ``state``'s blobs.

    Only chunks named by the manifest's ``includes`` are read — the same
    live/archived boundary the roadmap loader enforces, so an archived chunk
    still on disk stays out of the reconstruction.
    """
    manifest = reader.json(state.get(MANIFEST_REL) or "")
    includes = manifest.get("includes") if isinstance(manifest, dict) else None
    if not isinstance(includes, list):
        return {}
    nodes: list[dict[str, Any]] = []
    for rel in includes:
        if not isinstance(rel, str) or not rel.strip():
            continue
        path = _include_path(rel.strip())
        sha = state.get(path) if path else None
        if sha:
            nodes.extend(nodes_from_chunk_doc(reader.json(sha)) or [])
    return snapshot(nodes)


def build_ledger(reader: BlobReader, state: dict[str, str]) -> dict[str, Any]:
    doc = reader.json(state.get(ARCHIVE_INDEX_REL) or "")
    return doc if isinstance(doc, dict) else {}


def _is_graph_path(path: str) -> bool:
    return (
        path == MANIFEST_REL
        or (
            path.startswith(ROADMAP_PREFIX)
            and path.endswith(".json")
            and not path.startswith(ARCHIVE_PREFIX)
        )
    )


def _sheet_events(commit: Commit) -> list[dict[str, Any]]:
    """Sheet touches, attributed straight from the filename's ``node_key``."""
    from specy_road.bundled_scripts.planning_artifacts import PLANNING_FILENAME_RE

    # One event per node per commit. Renumbering or recodenaming a node renames
    # its sheet, which --no-renames reports as a delete plus an add; both name
    # the same node, and "the sheet was touched" happened once. The surviving
    # path wins so the event points at a file that still exists.
    best: dict[str, tuple[bool, dict[str, Any]]] = {}
    for path, blob in commit.changes:
        if not path.startswith(PLANNING_PREFIX) or not path.endswith(".md"):
            continue
        match = PLANNING_FILENAME_RE.match(posixpath.basename(path))
        if match is None:
            continue
        key = match.group("uuid").lower()
        alive = blob is not None
        if key in best and not alive:
            continue
        best[key] = (
            alive,
            make_event(
                commit.meta(), key, SHEET_EDIT, id=match.group("id"), path=path
            ),
        )
    return [best[k][1] for k in sorted(best)]


@dataclass
class _Cursor:
    """Replay state: file blobs, plus the last graph and ledger built from them."""

    state: dict[str, str]
    graph: dict[str, dict[str, Any]]
    ledger: dict[str, Any]


def _apply(commit: Commit, cursor: _Cursor) -> tuple[bool, bool]:
    """Fold a commit's changes into the blob state. Returns what needs rebuilding."""
    graph_touched = archive_touched = False
    for path, blob in commit.changes:
        if blob is None:
            cursor.state.pop(path, None)
        else:
            cursor.state[path] = blob
        if path == ARCHIVE_INDEX_REL:
            archive_touched = True
        elif _is_graph_path(path):
            graph_touched = True
    return graph_touched, archive_touched


def _commit_events(
    commit: Commit, cursor: _Cursor, reader: BlobReader
) -> list[dict[str, Any]]:
    graph_touched, archive_touched = _apply(commit, cursor)
    meta = commit.meta()
    events = _sheet_events(commit)

    ledger_events: list[dict[str, Any]] = []
    archived: set[str] = set()
    restored: set[str] = set()
    if archive_touched:
        current = build_ledger(reader, cursor.state)
        ledger_events, archived, restored = archive_events(
            cursor.ledger, current, meta
        )
        cursor.ledger = current

    if graph_touched or archive_touched:
        current_graph = build_graph(reader, cursor.state)
        events.extend(
            reconcile_archive(
                diff_snapshots(cursor.graph, current_graph, meta), archived, restored
            )
        )
        cursor.graph = current_graph

    events.extend(ledger_events)
    return events


def walk(
    root: Path, since: str | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    """Events from ``since`` (exclusive) to ``HEAD``, plus the last commit seen.

    ``since`` seeds the file state from ``git ls-tree`` at that commit rather
    than from anything cached, so an incremental walk can never diff against a
    blob map that has drifted from what git actually holds.
    """


    prefix = project_prefix(root)
    text = log_raw(root, SCOPES, since)
    if text is None:
        return [], since
    commits = parse_log(text, prefix)
    if not commits:
        return [], since

    seed: dict[str, str] = {}
    if since:
        for path, sha in ls_tree_blobs(root, since, ROADMAP_PREFIX.rstrip("/")).items():
            rel = rebase_to_project(path, prefix)
            if rel is not None:
                seed[rel] = sha

    events: list[dict[str, Any]] = []
    with BlobReader(root) as reader:
        cursor = _Cursor(
            state=seed,
            graph=build_graph(reader, seed),
            ledger=build_ledger(reader, seed),
        )
        for commit in commits:
            events.extend(_commit_events(commit, cursor, reader))
    return events, commits[-1].sha
