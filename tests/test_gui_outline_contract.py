"""PM GUI outline/node mutation endpoints: response shapes and which ids change.

Pins the bodies the bundled UI relies on (string ``"true"`` on move, reorder,
delete and add; boolean ``true`` plus ``changed`` on indent/outdent) and that
every form renumbers only the node it moves unless the request passes
``renumber_outline: true`` (M21.1). ``/outline/group`` answers ``"true"`` plus
``id_map`` (M21.2).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.move_node_helpers import (
    NK_A,
    NK_A1,
    NK_A2,
    NK_A21,
    NK_A22,
    NK_A24,
    NK_A3,
    NK_B4,
    ids_by_key,
    lock_milestone,
    nodes_by_key,
    tree_bytes,
    unchanged_except,
    wide_fixture,
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    wide_fixture(tmp_path)
    return tmp_path


@pytest.fixture()
def client(repo: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(repo))
    from specy_road.gui_app import create_app

    return TestClient(create_app())


def _post(client: TestClient, url: str, body: dict | list | bytes | None = None):
    """``bytes`` are sent as-is under ``Content-Type: application/json``."""
    fp = client.get("/api/roadmap").json()["fingerprint"]
    kw: dict = {"headers": {"X-PM-Gui-Fingerprint": str(fp)}}
    if isinstance(body, bytes):
        kw["headers"]["Content-Type"] = "application/json"
        kw["content"] = body
    elif body is not None:
        kw["json"] = body
    return client.post(url, **kw)


@pytest.mark.parametrize(
    ("extra", "expected"),
    [
        ({}, {NK_A22: "M2.5"}),
        ({"new_id": "M2.3"}, {NK_A22: "M2.3"}),
        ({"fill_gaps": True}, {NK_A22: "M2.2"}),
    ],
    ids=["default", "new_id", "fill_gaps"],
)
def test_outline_move_renumbers_only_the_moved_node(
    client: TestClient, repo: Path, extra: dict, expected: dict[str, str]
) -> None:
    before = ids_by_key(repo)
    body = {"node_key": NK_A22, "new_parent_id": "M2", "new_index": 0, **extra}

    r = _post(client, "/api/outline/move", body)

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": "true"}
    after = ids_by_key(repo)
    assert {k: after[k] for k in expected} == expected
    assert unchanged_except(before, after, set(expected))


def test_outline_move_renumber_outline_renumbers_the_whole_outline(
    client: TestClient, repo: Path
) -> None:
    body = {"node_key": NK_A22, "new_parent_id": "M2", "new_index": 0, "renumber_outline": True}

    r = _post(client, "/api/outline/move", body)

    assert r.status_code == 200, r.text
    after = ids_by_key(repo)
    assert (after[NK_A22], after[NK_A24], after[NK_B4]) == ("M2.1", "M1.2.2", "M2.3")


@pytest.mark.parametrize(
    "body",
    [
        {"node_key": "00000000-0000-4000-8000-000000000000", "new_parent_id": "M2"},
        {"node_key": NK_A22, "new_parent_id": "M2", "new_id": "M2.4"},
        {"node_key": NK_A22, "new_parent_id": "M2", "new_id": "M2.2", "fill_gaps": True},
        {"node_key": NK_A22, "new_parent_id": "M2", "fill_gaps": True, "renumber_outline": True},
    ],
    ids=["unknown-node-key", "taken", "id-with-fill-gaps", "fill-gaps-with-renumber"],
)
def test_outline_move_refusals_are_400_with_a_string_detail(
    client: TestClient, repo: Path, body: dict
) -> None:
    before = ids_by_key(repo)

    r = _post(client, "/api/outline/move", body)

    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)
    assert ids_by_key(repo) == before


def test_outline_group_returns_the_id_map(client: TestClient, repo: Path) -> None:
    before = ids_by_key(repo)
    body = {"into_new": "M1.4", "title": "Grouped", "node_ids": ["M1.3", "M1.2"]}

    r = _post(client, "/api/outline/group", body)

    assert r.status_code == 200, r.text
    assert r.json() == {
        "ok": "true",
        "id_map": {
            "M1.3": "M1.4.1",
            "M1.2": "M1.4.2",
            "M1.2.1": "M1.4.2.1",
            "M1.2.2": "M1.4.2.2",
            "M1.2.4": "M1.4.2.4",
        },
    }
    after = ids_by_key(repo)
    moved = {NK_A3, NK_A2, NK_A21, NK_A22, NK_A24}
    new_key = (set(after) - set(before)).pop()
    assert after[new_key] == "M1.4"
    assert nodes_by_key(repo)[new_key]["type"] == "milestone"
    del after[new_key]
    assert unchanged_except(before, after, moved)


def test_outline_group_into_an_id_a_listed_node_holds(client: TestClient, repo: Path) -> None:
    body = {"into_new": "M1.2", "title": "Grouped", "node_ids": ["M1.2", "M1.3"]}

    r = _post(client, "/api/outline/group", body)

    assert r.status_code == 200, r.text
    assert r.json() == {
        "ok": "true",
        "id_map": {
            "M1.2": "M1.2.1",
            "M1.2.1": "M1.2.1.1",
            "M1.2.2": "M1.2.1.2",
            "M1.2.4": "M1.2.1.4",
            "M1.3": "M1.2.2",
        },
    }
    after = ids_by_key(repo)
    assert (after[NK_A1], after[NK_A2], after[NK_A3]) == ("M1.1", "M1.2.1", "M1.2.2")


@pytest.mark.parametrize(
    "body",
    [
        {"into_new": "M1.4", "title": "G", "node_ids": ["M9"]},
        {"into_new": "M1.4", "title": "G", "node_ids": []},
        {"into_new": "M1.4", "title": "G", "node_ids": ["M1.1", "M1.1"]},
        {"into_new": "M1.4", "title": "G", "node_ids": ["M1.1", "M2.1"]},
        {"into_new": "M1.3", "title": "G", "node_ids": ["M1.1"]},
        {"into_new": "M1.4", "title": "", "node_ids": ["M1.1"]},
        {"into_new": "M1.4", "title": "G", "node_ids": ["M1.1"], "type": "gate"},
        {"into_new": "M1.4", "title": "G", "node_ids": ["M1.1"], "type": "epic"},
        None,
        {},
        [],
        {"into_new": "M1.4", "node_ids": ["M1.1"]},
        {"into_new": "M1.4", "title": "G", "node_ids": "M1.1"},
        b"{",
        b"not json",
    ],
    ids=[
        "unknown", "empty", "duplicate", "not-siblings", "taken", "empty-title",
        "gate-parent", "unknown-type", "no-body", "empty-body", "list-body",
        "missing-title", "ids-not-a-list", "truncated-json", "not-json",
    ],
)
def test_outline_group_refusals_are_400_with_a_string_detail(
    client: TestClient, repo: Path, body: dict | list | bytes | None
) -> None:
    before = tree_bytes(repo)

    r = _post(client, "/api/outline/group", body)

    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)
    assert tree_bytes(repo) == before


def test_outline_group_under_a_locked_milestone_is_a_400_refusal(
    client: TestClient, repo: Path
) -> None:
    lock_milestone(repo, NK_A)
    before = tree_bytes(repo)
    body = {"into_new": "M1.4", "title": "G", "node_ids": ["M1.1"]}

    r = _post(client, "/api/outline/group", body)

    assert r.status_code == 400
    assert "active milestone execution" in r.json()["detail"]
    assert tree_bytes(repo) == before


def test_outline_reorder_changes_sibling_order_only(client: TestClient, repo: Path) -> None:
    before = ids_by_key(repo)

    r = _post(client, "/api/outline/reorder", {"parent_id": "M1", "ordered_child_ids": ["M1.3", "M1.2", "M1.1"]})

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": "true"}
    assert ids_by_key(repo) == before
    roadmap = client.get("/api/roadmap").json()["nodes"]
    order = {n["node_key"]: n["sibling_order"] for n in roadmap}
    assert (order[NK_A3], order[NK_A2], order[NK_A1]) == (0, 1, 2)


def test_outline_reorder_renumber_outline_renumbers(client: TestClient, repo: Path) -> None:
    body = {"parent_id": "M1", "ordered_child_ids": ["M1.3", "M1.2", "M1.1"], "renumber_outline": True}

    r = _post(client, "/api/outline/reorder", body)

    assert r.status_code == 200, r.text
    after = ids_by_key(repo)
    assert (after[NK_A3], after[NK_A2], after[NK_A1]) == ("M1.1", "M1.2", "M1.3")
    assert after[NK_B4] == "M2.2"


def test_outline_reorder_refusal_is_400_with_a_string_detail(client: TestClient) -> None:
    r = _post(client, "/api/outline/reorder", {"parent_id": "M1", "ordered_child_ids": ["M1.1"]})

    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)


@pytest.mark.parametrize("body", [None, {}, {"renumber_outline": False}], ids=["no-body", "empty", "explicit"])
@pytest.mark.parametrize(
    ("url", "moved", "new_id"),
    [
        # M1.3 nests under M1.2 and takes the next free id there.
        ("/api/nodes/M1.3/indent", NK_A3, "M1.2.5"),
        # M1.2.4 becomes M1's next free child.
        ("/api/nodes/M1.2.4/outdent", NK_A24, "M1.4"),
    ],
    ids=["indent", "outdent"],
)
def test_indent_and_outdent_renumber_only_the_moved_node(
    client: TestClient, repo: Path, url: str, moved: str, new_id: str, body: dict | None
) -> None:
    before = ids_by_key(repo)

    r = _post(client, url, body)

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "changed": True}
    after = ids_by_key(repo)
    assert after[moved] == new_id
    assert unchanged_except(before, after, {moved})


def test_indent_with_renumber_outline_renumbers(client: TestClient, repo: Path) -> None:
    r = _post(client, "/api/nodes/M1.3/indent", {"renumber_outline": True})

    assert r.status_code == 200, r.text
    after = ids_by_key(repo)
    assert (after[NK_A3], after[NK_A24], after[NK_B4]) == ("M1.2.4", "M1.2.3", "M2.2")


def test_indent_noop_reports_unchanged(client: TestClient) -> None:
    r = _post(client, "/api/nodes/M1.1/indent")

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "changed": False}


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("post", "/api/nodes/M9/indent", None),
        ("post", "/api/nodes/M9/outdent", None),
        ("delete", "/api/nodes/M9", None),
        ("post", "/api/nodes/add", {"reference_node_id": "M9", "position": "below", "title": "x", "type": "task"}),
    ],
    ids=["indent", "outdent", "delete", "add"],
)
def test_an_unknown_node_is_400(client: TestClient, method: str, url: str, body: dict | None) -> None:
    fp = client.get("/api/roadmap").json()["fingerprint"]
    kw: dict = {"headers": {"X-PM-Gui-Fingerprint": str(fp)}}
    if body is not None:
        kw["json"] = body

    r = getattr(client, method)(url, **kw)

    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)


def test_delete_shape(client: TestClient) -> None:
    fp = client.get("/api/roadmap").json()["fingerprint"]

    r = client.delete("/api/nodes/M2.4", headers={"X-PM-Gui-Fingerprint": str(fp)})

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": "true", "node_id": "M2.4"}


@pytest.mark.parametrize(
    ("extra", "new_id"),
    [({}, "M2.5"), ({"new_id": "M2.2"}, "M2.2")],
    ids=["next-free", "requested"],
)
def test_add_node_takes_a_free_id_and_changes_no_other(
    client: TestClient, repo: Path, extra: dict, new_id: str
) -> None:
    before = ids_by_key(repo)
    body = {"reference_node_id": "M2.1", "position": "above", "title": "Added", "type": "task", **extra}

    r = _post(client, "/api/nodes/add", body)

    assert r.status_code == 200, r.text
    assert r.json() == {"ok": "true", "id": new_id}
    after = ids_by_key(repo)
    added = set(after) - set(before)
    assert [after[k] for k in added] == [new_id]
    assert {k: after[k] for k in before} == before


def test_add_node_refuses_a_taken_requested_id(client: TestClient, repo: Path) -> None:
    before = ids_by_key(repo)
    body = {"reference_node_id": "M2.1", "position": "below", "title": "Added", "type": "task", "new_id": "M2.4"}

    r = _post(client, "/api/nodes/add", body)

    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)
    assert ids_by_key(repo) == before
