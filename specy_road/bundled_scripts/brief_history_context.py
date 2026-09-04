"""The ``## 9. History`` brief section: how this node got to where it is.

A brief already tells an implementing agent what the node *is*. This tells it
what the node has *been* — the statuses it passed through, the dependency edges
that were added and later dropped, the ids it has carried, and the sibling work
that was archived out from under it. That last one is invisible any other way:
archived nodes are gone from the live graph and from ``roadmap.md``, so without
this an agent cannot know a phase was ever larger than it looks.

Everything is derived from git via :mod:`specy_road.history_index`. The section
carries **no wall-clock values** — only commit dates and SHAs — so a brief
rendered twice at the same ``HEAD`` is byte-identical, which
``test_render_brief_is_deterministic`` depends on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

HEADER = "## 9. History (derived from git)"

# Enough to see a pattern without turning the brief into a changelog.
_MAX_STATUS = 6
_MAX_DEPS = 6
_MAX_SHEET_COMMITS = 3


def _ancestor_ids(node_id: str) -> list[str]:
    parts = node_id.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def _parent_id(node_id: str) -> str:
    return node_id.rpartition(".")[0]


def is_related(node_id: str, other_id: str) -> bool:
    """Whether an archived node sits on this node's branch of the outline.

    Ancestors, descendants and siblings all count. A descendant matters most:
    archiving children is how a phase quietly shrinks, and its parent's brief is
    exactly where someone needs to learn the phase used to be bigger. An archive
    elsewhere in the roadmap is noise in a brief and is left out.
    """
    if not other_id or other_id == node_id:
        return False
    if other_id in _ancestor_ids(node_id):
        return True
    if other_id.startswith(f"{node_id}."):
        return True
    parent = _parent_id(node_id)
    return bool(parent) and _parent_id(other_id) == parent


def _title_for_key(key: str, by_id: dict[str, dict]) -> str:
    for node in by_id.values():
        if node.get("node_key") == key:
            return f"{node.get('id')} — {node.get('title') or '(no title)'}"
    return f"`{key}` (not in the live graph — archived or removed)"


def _status_lines(timeline: list[dict[str, Any]]) -> list[str]:
    events = [e for e in timeline if e["kind"] == "status"][-_MAX_STATUS:]
    if not events:
        return []
    out = ["**Status history**", ""]
    for event in events:
        was = event.get("from") or "(unset)"
        out.append(
            f"- {str(event.get('at'))[:10]} `{str(event.get('commit'))[:8]}` "
            f"{was} → {event.get('to')}"
        )
    return [*out, ""]


def _dependency_lines(
    timeline: list[dict[str, Any]], by_id: dict[str, dict]
) -> list[str]:
    events = [
        e for e in timeline if e["kind"] in ("dep_added", "dep_removed")
    ][-_MAX_DEPS:]
    if not events:
        return []
    out = ["**Dependency changes**", ""]
    for event in events:
        added = event["kind"] == "dep_added"
        key = event.get("to") if added else event.get("from")
        verb = "added" if added else "removed"
        out.append(
            f"- {str(event.get('at'))[:10]} `{str(event.get('commit'))[:8]}` "
            f"{verb} dependency on {_title_for_key(str(key), by_id)}"
        )
    out.append("")
    out.append(
        "_A removed dependency is a decision someone already made. Check why "
        "before re-adding it._"
    )
    return [*out, ""]


def _renumber_lines(timeline: list[dict[str, Any]]) -> list[str]:
    events = [e for e in timeline if e["kind"] == "renumbered"]
    if not events:
        return []
    trail = " → ".join(
        [str(events[0].get("from"))] + [str(e.get("to")) for e in events]
    )
    return [
        "**This node has been renumbered**",
        "",
        f"- ids over time: {trail}",
        "",
        "_Older commits, briefs and PRs refer to it by its earlier id._",
        "",
    ]


def _sheet_lines(timeline: list[dict[str, Any]]) -> list[str]:
    events = [e for e in timeline if e["kind"] == "sheet_edit"]
    if not events:
        return []
    recent = ", ".join(f"`{str(e.get('commit'))[:8]}`" for e in events[-_MAX_SHEET_COMMITS:])
    plural = "commit" if len(events) == 1 else "commits"
    return [
        f"**Planning sheet**: revised in {len(events)} {plural}; "
        f"most recent {recent}.",
        "",
    ]


def _archive_lines(node: dict, index: dict[str, Any]) -> list[str]:
    from specy_road.history_index import archive_history

    node_id = str(node.get("id") or "")
    related = [
        e
        for e in archive_history(index)
        if is_related(node_id, str(e.get("id") or ""))
    ]
    if not related:
        return []
    out = ["**Related work that left the live roadmap**", ""]
    seen: set[str] = set()
    for event in related:
        archive_id = str(event.get("archive_id") or "")
        if archive_id in seen:
            continue
        seen.add(archive_id)
        verb = "archived" if event["kind"] == "archived" else "restored"
        out.append(
            f"- {str(event.get('at'))[:10]} {event.get('id')} {verb} "
            f"(`specy-road show-archive {archive_id}`)"
        )
    out.append("")
    out.append(
        "_These are not in the live graph. Inspect them before assuming this "
        "area was never built._"
    )
    return [*out, ""]


def render_history_section(
    node: dict, by_id: dict[str, dict], repo_root: Path
) -> list[str]:
    """Build ``## 9. History``.

    Always emits the header so downstream tooling has a stable landmark, and
    degrades to one explanatory line when git cannot answer — a tarball export,
    a fresh checkout with no commits, or a directory that is not a worktree.
    """
    from specy_road.history_index import history_index, node_timeline

    out = [HEADER, ""]
    key = node.get("node_key")
    if not isinstance(key, str) or not key:
        return [*out, "_(this node has no `node_key`, so it cannot be tracked)_", ""]

    try:
        index = history_index(repo_root)
    except Exception:  # noqa: BLE001 - history is context, never fatal to a brief
        index = {"events": [], "head": None}

    if not index.get("events"):
        return [
            *out,
            "_(no git history available — this is derived from commits, not stored)_",
            "",
        ]

    timeline = node_timeline(index, key)
    body = [
        *_renumber_lines(timeline),
        *_status_lines(timeline),
        *_dependency_lines(timeline, by_id),
        *_sheet_lines(timeline),
        *_archive_lines(node, index),
    ]
    if not body:
        return [*out, "_(nothing recorded for this node yet)_", ""]
    return [*out, *body]
