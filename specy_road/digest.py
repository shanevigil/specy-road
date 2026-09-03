"""Render the current-state digest: what the roadmap says *right now*.

An agentic IDE indexing a long-running specy-road project drowns in
duplication — a brief inlines its ancestor sheets and every ``shared/*.md``,
a pr-body re-inlines the whole brief, and archived work has vanished from the
live graph entirely. The digest is the antidote: one small, generated,
git-tracked document that the IDE *should* index, standing in for the large
corpus it should not.

Everything here is derived from sources that already exist — the merged graph,
the archive ledger, the git-derived history index, and the claim registry — so
the digest has nothing of its own to go stale. It is deterministic for a given
working tree and HEAD: absolute ISO dates only, no wall-clock values, so
``--check`` can be a CI drift gate the way ``export --check`` already is.

Every optional source is best-effort. A repo with no git history, no archive and
no claims still renders a complete digest of its live graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.registry_yaml import read_registry, registry_path
from specy_road.archive_index import records_or_empty
from specy_road.node_kinds import is_gate

BANNER = (
    "<!-- specy-road: generated context digest — do not edit by hand. "
    "Regenerate with `specy-road digest`. -->"
)
DEFAULT_OUTPUT = "roadmap-context.md"

# A digest is only useful if an agent reads all of it, so the long tail of each
# unbounded section is summarised rather than listed.
_MAX_DROPPED_DEPS = 25
_MAX_ARCHIVES = 40


def _load_nodes(root: Path) -> list[dict[str, Any]]:
    from specy_road.archive_plan import ensure_bundled_scripts_on_path

    ensure_bundled_scripts_on_path()
    from roadmap_load import load_roadmap

    return load_roadmap(root)["nodes"]


def _status_of(node: dict[str, Any]) -> str:
    rollup = node.get("rollup_status")
    if isinstance(rollup, str) and rollup:
        return rollup
    return str(node.get("status") or "")


def _key_to_node(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        n["node_key"]: n for n in nodes if isinstance(n.get("node_key"), str)
    }


def _label(node: dict[str, Any]) -> str:
    return f"{node.get('id')} {node.get('title') or '(no title)'}"


def _section_outline(nodes: list[dict[str, Any]]) -> list[str]:
    """The live graph as an indented outline with rolled-up status."""
    from roadmap_layout import ordered_tree_rows

    out = [
        "## Live roadmap",
        "",
        "Status is the computed rollup: a non-leaf is Complete only when every "
        "leaf descendant is.",
        "",
    ]
    rows = ordered_tree_rows(nodes)
    if not rows:
        return [*out, "_(no nodes in the live graph)_", ""]
    for node, depth in rows:
        indent = "  " * depth
        codename = node.get("codename")
        suffix = f" `{codename}`" if codename else ""
        out.append(
            f"{indent}- `{node.get('id')}` {node.get('title') or '(no title)'}"
            f"{suffix} — {node.get('type')} — **{_status_of(node)}**"
        )
    return [*out, ""]


def _section_decisions(nodes: list[dict[str, Any]]) -> list[str]:
    """Decisions already taken — the thing an agent must not silently redo."""
    from roadmap_layout import natural_id_sort_key

    decided = [
        n
        for n in nodes
        if isinstance(n.get("decision"), dict)
        and n["decision"].get("status") == "decided"
    ]
    pending = [
        n
        for n in nodes
        if isinstance(n.get("decision"), dict)
        and n["decision"].get("status") == "pending"
    ]
    if not decided and not pending:
        return []

    out = ["## Decisions", ""]
    for node in sorted(decided, key=lambda n: natural_id_sort_key(n["id"])):
        decision = node["decision"]
        when = decision.get("decided_date") or "date not recorded"
        ref = decision.get("adr_ref")
        tail = f" — see {ref}" if ref else ""
        out.append(f"- **Decided** {when}: `{_label(node)}`{tail}")
    for node in sorted(pending, key=lambda n: natural_id_sort_key(n["id"])):
        out.append(f"- **Pending**: `{_label(node)}` — not yet decided")
    return [*out, ""]


def _section_open_gates(nodes: list[dict[str, Any]]) -> list[str]:
    """Gates still holding work back."""
    from roadmap_layout import natural_id_sort_key

    gates = [
        n
        for n in nodes
        if is_gate(n.get("type")) and _status_of(n) != "Complete"
    ]
    if not gates:
        return []
    out = [
        "## Open gates",
        "",
        "Work behind these is deliberately held back until they clear.",
        "",
    ]
    for node in sorted(gates, key=lambda n: natural_id_sort_key(n["id"])):
        out.append(f"- `{_label(node)}` — **{_status_of(node)}**")
    return [*out, ""]


def _section_dropped_dependencies(
    root: Path, nodes: list[dict[str, Any]]
) -> list[str]:
    """Dependency edges that were added and later removed.

    The highest-value anti-rework signal in the whole digest: a removed edge is
    a decision someone already made, and it is invisible in the current graph
    precisely because it was removed.
    """
    events = _history_events(root, kinds={"dep_removed"})
    if not events:
        return []
    by_key = _key_to_node(nodes)
    out = [
        "## Dependencies that were removed",
        "",
        "Someone deliberately dropped these. Check why before re-adding one.",
        "",
    ]
    for event in events[:_MAX_DROPPED_DEPS]:
        dropped = str(event.get("from") or "")
        target = by_key.get(dropped)
        name = f"`{_label(target)}`" if target else f"`{dropped}` (no longer live)"
        out.append(
            f"- {str(event.get('at'))[:10]} `{event.get('id')}` "
            f"stopped depending on {name}"
        )
    if len(events) > _MAX_DROPPED_DEPS:
        out.append(
            f"- _…and {len(events) - _MAX_DROPPED_DEPS} earlier — "
            "`specy-road history --json`_"
        )
    return [*out, ""]


def _history_events(root: Path, *, kinds: set[str]) -> list[dict[str, Any]]:
    """Newest-first events of the given kinds, or empty when git cannot answer."""
    try:
        from specy_road.history_index import feed, history_index

        return feed(history_index(root), kinds=kinds)
    except Exception:  # noqa: BLE001 - history is context, never fatal
        return []


def _section_archived(root: Path) -> list[str]:
    """Work that left the live graph — invisible everywhere else."""
    records = records_or_empty(root)
    if not records:
        return []

    out = [
        "## Archived (not in the live roadmap)",
        "",
        "This work was completed and moved out of the graph. It is deliberately "
        "excluded from IDE indexing; reach it with "
        "`specy-road search <QUERY> --scope archived`.",
        "",
    ]
    ordered = sorted(
        records, key=lambda r: (str(r.get("archived_at") or ""), str(r.get("archive_id")))
    )
    for record in ordered[:_MAX_ARCHIVES]:
        count = len(record.get("node_keys") or [])
        plural = "node" if count == 1 else "nodes"
        out.append(
            f"- {str(record.get('archived_at'))[:10]} "
            f"`{record.get('root_node_id')}` ({count} {plural}) — "
            f"`specy-road show-archive {record.get('archive_id')}`"
        )
    if len(ordered) > _MAX_ARCHIVES:
        out.append(
            f"- _…and {len(ordered) - _MAX_ARCHIVES} more — `specy-road list-archives`_"
        )
    return [*out, ""]


def _section_claims(root: Path) -> list[str]:
    """Nodes someone is actively working on right now."""
    try:
        from specy_road.archive_plan import ensure_bundled_scripts_on_path

        ensure_bundled_scripts_on_path()

        entries = read_registry(registry_path(root)).get("entries") or []
    except Exception:  # noqa: BLE001 - the registry is advisory here
        return []
    entries = [e for e in entries if isinstance(e, dict) and e.get("node_id")]
    if not entries:
        return []
    out = ["## Claimed and in flight", "", "Do not pick these up.", ""]
    for entry in sorted(entries, key=lambda e: str(e.get("node_id"))):
        branch = entry.get("branch") or "(no branch)"
        started = str(entry.get("started") or "")[:10]
        out.append(
            f"- `{entry.get('node_id')}` on `{branch}`"
            + (f" since {started}" if started else "")
        )
    return [*out, ""]


def _section_footer() -> list[str]:
    return [
        "## Reaching the detail behind this",
        "",
        "This digest is a summary. The full text of planning sheets, shared "
        "contracts and archived work is searchable:",
        "",
        "```bash",
        "specy-road search \"<query>\"                 # live + archived, ranked",
        "specy-road search \"<query>\" --scope archived  # completed work only",
        "specy-road search <NODE_ID>                  # everything about one node",
        "specy-road history <NODE_ID>                 # how it got to this state",
        "```",
        "",
    ]


def render_digest(root: Path) -> str:
    """The whole digest, deterministic for a given working tree and HEAD."""
    nodes = _load_nodes(root)
    parts: list[list[str]] = [
        ["# Roadmap context", "", BANNER, ""],
        [
            "The current state of this project's roadmap, generated from the "
            "merged graph, the archive ledger and git history. Read this before "
            "crawling `planning/` or `work/` — it is the authoritative summary, "
            "and those directories contain a great deal of duplicated text.",
            "",
        ],
        _section_outline(nodes),
        _section_decisions(nodes),
        _section_open_gates(nodes),
        _section_dropped_dependencies(root, nodes),
        _section_archived(root),
        _section_claims(root),
        _section_footer(),
    ]
    body = "\n".join("\n".join(part) for part in parts if part)
    return body.rstrip() + "\n"
