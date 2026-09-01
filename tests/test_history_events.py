"""The graph diff behind `specy-road history`.

Pure dict-in/dict-out, so every interesting case is expressible without a git
repository. The property worth pinning hardest is that history follows
``node_key`` and not ``id`` — a renumbered node must keep one continuous story.
"""

from __future__ import annotations

from typing import Any

from specy_road.history_events import (
    ARCHIVED,
    CREATED,
    DEP_ADDED,
    DEP_REMOVED,
    REMOVED,
    RENUMBERED,
    REPARENTED,
    RESTORED,
    RETITLED,
    STATUS,
    archive_events,
    diff_snapshots,
    node_state,
    reconcile_archive,
    snapshot,
)

KEY_A = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
KEY_B = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"
META = {"commit": "c0ffee", "at": "2026-02-11T09:03:11-07:00", "author": "pat"}


def node(key: str = KEY_A, **over: Any) -> dict[str, Any]:
    base = {
        "id": "M1.1",
        "node_key": key,
        "type": "milestone",
        "title": "Retry queue",
        "status": "Not Started",
        "parent_id": "M1",
        "dependencies": [],
    }
    base.update(over)
    return base


def kinds(events: list[dict[str, Any]]) -> list[str]:
    return [e["kind"] for e in events]


def only(events: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    matched = [e for e in events if e["kind"] == kind]
    assert len(matched) == 1, f"expected exactly one {kind}, got {kinds(events)}"
    return matched[0]


def test_snapshot_is_keyed_by_node_key_and_skips_nodes_without_one() -> None:
    snap = snapshot([node(), {"id": "M2", "title": "no key"}])
    assert list(snap) == [KEY_A]


def test_node_state_sorts_dependencies_so_reordering_is_not_a_change() -> None:
    a = node_state(node(dependencies=[KEY_B, "cccccccc-3333-4333-8333-cccccccccccc"]))
    b = node_state(node(dependencies=["cccccccc-3333-4333-8333-cccccccccccc", KEY_B]))
    assert a == b


def test_a_new_node_key_is_created() -> None:
    events = diff_snapshots({}, snapshot([node()]), META)
    ev = only(events, CREATED)
    assert ev["node_key"] == KEY_A
    assert ev["id"] == "M1.1"
    assert ev["title"] == "Retry queue"
    assert ev["commit"] == "c0ffee"
    assert ev["at"] == META["at"]
    assert ev["author"] == "pat"


def test_a_vanished_node_key_is_removed() -> None:
    events = diff_snapshots(snapshot([node()]), {}, META)
    assert only(events, REMOVED)["node_key"] == KEY_A


def test_status_transition_records_both_ends() -> None:
    before = snapshot([node()])
    after = snapshot([node(status="In Progress")])

    ev = only(diff_snapshots(before, after, META), STATUS)
    assert ev["from"] == "Not Started"
    assert ev["to"] == "In Progress"


def test_renumbering_is_an_event_not_a_new_node() -> None:
    """The whole reason history is keyed by node_key."""
    before = snapshot([node(id="M1.4")])
    after = snapshot([node(id="M1.2")])

    events = diff_snapshots(before, after, META)

    assert kinds(events) == [RENUMBERED]
    assert CREATED not in kinds(events) and REMOVED not in kinds(events)
    ev = events[0]
    assert (ev["from"], ev["to"]) == ("M1.4", "M1.2")


def test_retitle_and_reparent_are_distinct_kinds() -> None:
    before = snapshot([node()])
    after = snapshot([node(title="Payment retry queue", parent_id="M2")])

    events = diff_snapshots(before, after, META)

    assert set(kinds(events)) == {RETITLED, REPARENTED}
    assert only(events, REPARENTED)["to"] == "M2"


def test_dependency_edges_are_added_and_removed_individually() -> None:
    before = snapshot([node(dependencies=[KEY_B])])
    after = snapshot([node(dependencies=["cccccccc-3333-4333-8333-cccccccccccc"])])

    events = diff_snapshots(before, after, META)

    assert only(events, DEP_REMOVED)["from"] == KEY_B
    assert only(events, DEP_ADDED)["to"].startswith("cccccccc")


def test_an_unchanged_graph_produces_nothing() -> None:
    snap = snapshot([node(), node(KEY_B, id="M1.2")])
    assert diff_snapshots(snap, snap, META) == []


def test_diff_is_deterministic_regardless_of_input_order() -> None:
    before = snapshot([node(), node(KEY_B, id="M1.2")])
    after_a = snapshot([node(status="Complete"), node(KEY_B, id="M1.2", title="x")])
    after_b = snapshot([node(KEY_B, id="M1.2", title="x"), node(status="Complete")])

    assert diff_snapshots(before, after_a, META) == diff_snapshots(before, after_b, META)


# --- archive ledger ---------------------------------------------------------


def ledger(*records: dict[str, Any]) -> dict[str, Any]:
    return {"version": 1, "records": list(records)}


def record(aid: str = "M1.1-aaaaaaaa-20260601") -> dict[str, Any]:
    return {
        "archive_id": aid,
        "root_node_id": "M1.1",
        "node_keys": [KEY_A],
        "nodes_summary": [{"id": "M1.1", "node_key": KEY_A, "title": "Retry queue"}],
    }


def test_a_new_ledger_record_archives_every_node_it_names() -> None:
    events, archived, restored = archive_events({}, ledger(record()), META)

    assert kinds(events) == [ARCHIVED]
    assert archived == {KEY_A} and restored == set()
    assert events[0]["archive_id"] == "M1.1-aaaaaaaa-20260601"
    assert events[0]["root_node_id"] == "M1.1"
    assert events[0]["id"] == "M1.1"


def test_a_dropped_ledger_record_restores_its_nodes() -> None:
    events, archived, restored = archive_events(ledger(record()), ledger(), META)

    assert kinds(events) == [RESTORED]
    assert restored == {KEY_A} and archived == set()


def test_archiving_suppresses_the_bare_removed_event() -> None:
    """Archived work was not deleted, and the ledger event says more."""
    graph = diff_snapshots(snapshot([node()]), {}, META)
    assert kinds(graph) == [REMOVED]

    assert reconcile_archive(graph, {KEY_A}, set()) == []


def test_restoring_suppresses_the_bare_created_event() -> None:
    graph = diff_snapshots({}, snapshot([node()]), META)
    assert reconcile_archive(graph, set(), {KEY_A}) == []


def test_reconcile_keeps_genuine_creations_and_deletions() -> None:
    """A hard delete is real history and must survive reconciliation."""
    graph = diff_snapshots(snapshot([node()]), {}, META)

    assert reconcile_archive(graph, {KEY_B}, set()) == graph
