"""RoadmapIndex answers every graph query from one builder-made graph.

The graph covers what readiness has to get right: dependencies inherited from
an ancestor phase, a gate dependency, a milestone between a phase and its
leaves, lookups by stable ``node_key``, and outline order that differs from id
order (``sibling_order`` puts M2.2 before M2.1).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from specy_road.roadmap_index import RoadmapIndex


def _key(node_id: str) -> str:
    """A stable, valid node_key per display id (uuid4 shape)."""
    digits = "".join(c for c in node_id if c.isdigit()).ljust(12, "0")
    return f"40000000-0000-4000-8000-{digits}"


def _node(node_id: str, parent: str | None, kind: str = "task", *,
          deps: tuple[str, ...] = (), **fields: object) -> dict:
    """One node; ``fields`` (``status``, ``sibling_order``) override the defaults."""
    node = {
        "id": node_id, "node_key": _key(node_id), "parent_id": parent, "type": kind,
        "title": node_id, "status": "Not Started", "dependencies": [_key(d) for d in deps],
    }
    if kind == "task":
        node["codename"] = f"leaf-{node_id.replace('.', '-').lower()}"
    return {**node, **fields}


def _graph() -> list[dict]:
    return [
        _node("M1", None, "phase"),
        _node("M1.1", "M1", status="Complete"),
        _node("M1.2", "M1", "milestone"),
        _node("M1.2.1", "M1.2"),
        _node("M2", None, "phase", deps=("M1",)),
        _node("M2.1", "M2", "milestone", sibling_order=2),
        _node("M2.1.1", "M2.1", deps=("M3.1",)),
        _node("M2.1.2", "M2.1"),
        _node("M2.2", "M2", sibling_order=1),
        _node("M3", None, "phase"),
        _node("M3.1", "M3", "gate"),
    ]


def _ids(index: RoadmapIndex, keys) -> list[str]:
    return sorted(index.by_key[k]["id"] for k in keys)


#: M1.2.1 Complete on its feature branch and claimed: M1 rolls up Complete.
FINISHED_UPSTREAM = {"status_overrides": {_key("M1.2.1"): "complete"}, "claimed": {"M1.2.1"}}

ROWS: list[tuple[str, dict, Callable[[RoadmapIndex], object], object]] = [
    ("by id", {}, lambda ix: ix.by_id["M2.1.2"]["node_key"], _key("M2.1.2")),
    ("by stable key", {}, lambda ix: ix.by_key[_key("M3.1")]["id"], "M3.1"),
    ("milestone status is its leaves' rollup",
     {}, lambda ix: ix.status[_key("M1.2")], "not started"),
    ("phase status is its leaves' rollup", {}, lambda ix: ix.status[_key("M1")], "not started"),
    ("overrides flow up the rollup",
     FINISHED_UPSTREAM, lambda ix: ix.status[_key("M1")], "complete"),
    ("dependency inherited from the phase",
     {}, lambda ix: _ids(ix, ix.effective_dependencies[_key("M2.2")]), ["M1"]),
    ("inherited through a milestone, plus a gate",
     {}, lambda ix: _ids(ix, ix.effective_dependencies[_key("M2.1.1")]), ["M1", "M3.1"]),
    ("no dependencies", {}, lambda ix: _ids(ix, ix.effective_dependencies[_key("M1.2.1")]), []),
    ("unmet inherited dependency", {}, lambda ix: _ids(ix, ix.unmet(ix.by_id["M2.1.2"])), ["M1"]),
    ("met once upstream finishes", FINISHED_UPSTREAM, lambda ix: ix.unmet(ix.by_id["M2.1.2"]), []),
    ("an open gate stays unmet",
     FINISHED_UPSTREAM, lambda ix: _ids(ix, ix.unmet(ix.by_id["M2.1.1"])), ["M3.1"]),
    ("statuses given for one question", FINISHED_UPSTREAM,
     lambda ix: _ids(ix, ix.unmet(ix.by_id["M2.2"], RoadmapIndex(_graph()).status)), ["M1"]),
    ("ready: the one unblocked leaf", {}, lambda ix: [n["id"] for n in ix.ready()], ["M1.2.1"]),
    ("ready in outline order, gate and claimed left out",
     FINISHED_UPSTREAM, lambda ix: [n["id"] for n in ix.ready()], ["M2.2", "M2.1.2"]),
    ("outline order follows sibling_order", {},
     lambda ix: sorted(["M2.1", "M2.2"], key=ix.outline_position.__getitem__), ["M2.2", "M2.1"]),
]


@pytest.mark.parametrize(("question", "options", "ask", "expected"), ROWS, ids=[r[0] for r in ROWS])
def test_roadmap_index_answers(
    question: str, options: dict, ask: Callable[[RoadmapIndex], object], expected: object
) -> None:
    """Each row asks the index one question about the same graph."""
    assert ask(RoadmapIndex(_graph(), **options)) == expected, question
