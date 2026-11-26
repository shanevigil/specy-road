"""One public ``apply_set`` row for every whitelisted roadmap edit field.

``apply_set`` is the setter the edit-node CLI and the PM GUI share. The table
is the whole whitelist, so a new key shows up here as a missing row.
"""

from __future__ import annotations

import pytest

from specy_road.bundled_scripts.roadmap_edit_fields import EDIT_WHITELIST, apply_set

_NK = "20000000-0000-4000-8000-00000000ee01"
_OTHER = "20000000-0000-4000-8000-00000000ee02"
_IDS = {"M1", "M1.1", "M2"}
_KEYS = {_NK, _OTHER}

# key, raw value, path into the node, value the setter stores
SETTER_ROWS = (
    ("status", "Complete", ("status",), "Complete"),
    ("title", "Retitled alpha", ("title",), "Retitled alpha"),
    ("type", "milestone", ("type",), "milestone"),
    ("parent_id", "M2", ("parent_id",), "M2"),
    ("codename", "new-slug", ("codename",), "new-slug"),
    ("execution_milestone", "Human-led", ("execution_milestone",), "Human-led"),
    ("parallel_tracks", "3", ("parallel_tracks",), 3),
    ("sibling_order", "4", ("sibling_order",), 4),
    ("sensitivity", "internal", ("sensitivity",), "internal"),
    ("executor_eligibility", "agent", ("executor_eligibility",), "agent"),
    ("notes", "a note", ("notes",), "a note"),
    ("goal", "ship it", ("goal",), "ship it"),
    ("dependencies", _OTHER, ("dependencies",), [_OTHER]),
    ("touch_zones", "src/", ("touch_zones",), ["src/"]),
    ("acceptance", "the node moves", ("acceptance",), ["the node moves"]),
    ("risks", "low", ("risks",), ["low"]),
    (
        "planned_test_changes",
        "preserve: tests/scenarios/roadmap_edit/test_edit_fields.py::test_each_setter",
        ("planned_test_changes",),
        ["preserve: tests/scenarios/roadmap_edit/test_edit_fields.py::test_each_setter"],
    ),
    ("decision.status", "decided", ("decision", "status"), "decided"),
    ("decision.decided_date", "2026-11-08", ("decision", "decided_date"), "2026-11-08"),
    ("decision.adr_ref", "docs/adr/ADR-001.md", ("decision", "adr_ref"), "docs/adr/ADR-001.md"),
    ("planning_dir", "planning/custom.md", ("planning_dir",), "planning/custom.md"),
)


def fresh_node() -> dict:
    """A task whose codename was chosen, not derived from the title."""
    return {
        "id": "M1.1",
        "node_key": _NK,
        "parent_id": "M1",
        "type": "task",
        "title": "Alpha work",
        "codename": "chosen-name",
        "planning_dir": f"planning/M1.1_chosen-name_{_NK}.md",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "sibling_order": 0,
        "parallel_tracks": 1,
    }


def set_field(node: dict, key: str, raw: str) -> None:
    apply_set(
        node,
        key,
        raw,
        all_ids=_IDS,
        all_node_keys=_KEYS,
        self_id="M1.1",
    )


def test_the_setter_table_has_one_row_per_whitelisted_key() -> None:
    assert {key for key, *_rest in SETTER_ROWS} == set(EDIT_WHITELIST)


@pytest.mark.parametrize(
    ("key", "raw", "path", "expected"),
    SETTER_ROWS,
    ids=[row[0] for row in SETTER_ROWS],
)
def test_each_setter_writes_its_field(key: str, raw: str, path: tuple[str, ...], expected) -> None:
    node = fresh_node()

    set_field(node, key, raw)

    got = node
    for part in path:
        got = got[part]
    assert got == expected
    if key == "title":
        assert node["codename"] == "chosen-name"
    if key == "codename":
        assert node["planning_dir"] == f"planning/M1.1_new-slug_{_NK}.md"


def test_parent_id_null_clears_the_parent() -> None:
    node = fresh_node()

    set_field(node, "parent_id", "null")

    assert node["parent_id"] is None


@pytest.mark.parametrize(
    ("key", "raw", "message"),
    [
        ("type", "widget", "type must be one of"),
        ("parent_id", "M1.1", "cannot equal"),
        ("parent_id", "M9", "not an existing node id"),
        ("status", "Done", "status must be one of"),
        ("decision.status", "open", "decision.status must be one of"),
        ("codename", "Not Valid", "invalid codename"),
        ("execution_milestone", "Later", "execution_milestone must be one of"),
        ("parallel_tracks", "many", "parallel_tracks must be an integer"),
        ("sibling_order", "first", "sibling_order must be an integer"),
        ("sensitivity", "no spaces", "must be a single tag"),
        ("executor_eligibility", "bad tag", "must be a single tag"),
        ("dependencies", "not-a-key", "invalid dependency"),
        ("nope", "x", "key not allowed"),
    ],
)
def test_a_setter_refuses_a_value_the_field_does_not_allow(
    key: str, raw: str, message: str
) -> None:
    node = fresh_node()

    with pytest.raises(ValueError, match=message):
        set_field(node, key, raw)
