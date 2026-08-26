"""When each roadmap node was last worked on, derived from git history.

**Derived, never recorded.** There is no sidecar file: the answer is computed
from commit dates on demand. That removes a whole class of problems an
``activity.json`` had — a cold start on existing repos (nothing to seed,
because history is already there), a file that dirtied the working tree and
tripped the toolkit's own clean-tree checks, concurrent writers, and a schema
to migrate.

The signal, per node:

* **planning sheet** — the last commit touching ``planning_dir``. Per-node and
  precise; this is the primary answer.
* **chunk** — the last commit touching the roadmap chunk the node lives in,
  used *only* when the sheet has no date (never committed). It is deliberately
  not blended with the sheet date: a chunk holds many nodes, so crediting its
  date to all of them would make every sibling look freshly worked whenever one
  node's status changed, which is exactly the staleness signal the column
  exists to give.

Everything here is best-effort. A directory that is not a git repo, a missing
git binary, or a shallow clone yields fewer dated nodes, never an error.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

# Belt-and-braces bound on a pathological history. A node whose last touch is
# older than this is stale by any measure the column could express.
MAX_HISTORY_COMMITS = 50_000

SOURCE_PLANNING = "planning"
SOURCE_CHUNK = "chunk"

# Memo keyed by (repo path, HEAD sha). Commit dates only move when HEAD does,
# so this is exact rather than a TTL guess: an uncommitted edit cannot change
# any answer here. Bounded so a long-lived GUI process cannot grow without end.
_CACHE: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
_CACHE_MAX = 8


def _run_git(root: Path, args: list[str]) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    return r.stdout if r.returncode == 0 else None


def head_sha(root: Path) -> str | None:
    out = _run_git(root, ["rev-parse", "HEAD"])
    return (out or "").strip() or None


def last_commit_dates(root: Path, scopes: list[str]) -> dict[str, str]:
    """``{repo-relative path: ISO date}`` for everything under ``scopes``.

    One history walk, newest-first, so the first sighting of a path is its most
    recent touch. Asking git per path instead is linear in node count and
    unusably slow at the scale this targets: on a 400-node roadmap, per-path
    lookups take ~31s against ~0.17s for a single walk.

    ``--name-only`` without ``-m`` deliberately omits merge commits' file
    lists. A merge that only carries someone else's edit across is not the
    moment a node was worked on, and counting it would make every node look
    freshly touched after an integration merge.
    """
    if not scopes:
        return {}
    out = _run_git(
        root,
        [
            "log",
            f"--max-count={MAX_HISTORY_COMMITS}",
            "--format=@%aI",
            "--name-only",
            "--",
            *scopes,
        ],
    )
    if not out:
        return {}
    dates: dict[str, str] = {}
    current: str | None = None
    for line in out.splitlines():
        if line.startswith("@"):
            current = line[1:].strip()
        elif line.strip() and current and line not in dates:
            dates[line] = current
    return dates


def _scopes(paths: list[str]) -> list[str]:
    """Distinct parent directories, as git pathspecs.

    Passing directories rather than every file keeps argv small on a large
    roadmap while still restricting the walk to what we care about.
    """
    out = {str(Path(p).parent).replace("\\", "/") for p in paths}
    return sorted(s for s in out if s not in (".", ""))


def _chunk_rel_by_node_id(root: Path) -> dict[str, str]:
    """``{node_id: repo-relative chunk path}``, or empty when unavailable."""
    try:
        from roadmap_chunk_utils import build_node_chunk_map

        base = root.resolve()
        return {
            nid: p.resolve().relative_to(base).as_posix()
            for nid, p in build_node_chunk_map(root).items()
        }
    except Exception:  # noqa: BLE001 - activity is display metadata, never fatal
        return {}


def compute_node_activity(root: Path, nodes: list[dict]) -> dict[str, dict[str, str]]:
    """``{node_key: {at, source}}`` for every node git can date. Uncached."""
    sheets = {
        n["node_key"]: n["planning_dir"].strip()
        for n in nodes
        if isinstance(n.get("node_key"), str)
        and isinstance(n.get("planning_dir"), str)
        and n["planning_dir"].strip()
    }
    chunks = _chunk_rel_by_node_id(root)
    keyed_chunks = {
        n["node_key"]: chunks[n["id"]]
        for n in nodes
        if isinstance(n.get("node_key"), str) and chunks.get(n.get("id"))
    }

    sheet_dates = last_commit_dates(root, _scopes(list(sheets.values())))
    out: dict[str, dict[str, str]] = {}
    for key, sheet in sheets.items():
        when = sheet_dates.get(sheet)
        if when:
            out[key] = {"at": when, "source": SOURCE_PLANNING}

    undated = [k for k in keyed_chunks if k not in out]
    if undated:
        chunk_dates = last_commit_dates(
            root, _scopes([keyed_chunks[k] for k in undated])
        )
        for key in undated:
            when = chunk_dates.get(keyed_chunks[key])
            if when:
                out[key] = {"at": when, "source": SOURCE_CHUNK}
    return out


def node_activity(root: Path, nodes: list[dict]) -> dict[str, dict[str, str]]:
    """Cached :func:`compute_node_activity`, keyed on the repo's ``HEAD``."""
    sha = head_sha(root)
    if sha is None:
        # Not a git worktree (or no commits yet): nothing to derive, and no
        # stable cache key. Answer empty rather than re-walking every call.
        return {}
    key = (str(root.resolve()), sha)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    value = compute_node_activity(root, nodes)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = value
    return value


def clear_cache() -> None:
    """Drop the memo (tests, and after operations that rewrite history)."""
    _CACHE.clear()


def completed_at_from_activity(
    node: dict[str, Any], activity: dict[str, dict[str, str]]
) -> str | None:
    """The node's derived last-touch, for the auto-archive age threshold."""
    entry = activity.get(node.get("node_key"))
    at = entry.get("at") if isinstance(entry, dict) else None
    return at if isinstance(at, str) and at.strip() else None
