"""``planned_test_changes`` as an ``edit-node`` / ``add-node`` list field (M15.18).

Each item is checked against the item shape ``roadmap.schema.json`` gives the
field, so an edit is refused before it reaches the chunk file. Items are
integrity finding lines (``removed-test: tests/test_x.py::test_old``) or
red-green ``preserve: <path>::<name>`` lines; the schema, not this module, says
what an item may be.
"""

from __future__ import annotations

import json
from functools import cache

from jsonschema import Draft202012Validator

from specy_road.runtime_paths import specy_road_package_dir

PLANNED_TEST_CHANGES = "planned_test_changes"


@cache
def _item_validator() -> Draft202012Validator:
    path = specy_road_package_dir() / "templates" / "project" / "schemas" / "roadmap.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema["$defs"]["node"]["properties"][PLANNED_TEST_CHANGES]["items"])


def planned_test_change_items(values: list[str]) -> list[str]:
    """``values`` stripped, blanks dropped; ``ValueError`` names the first item the schema refuses."""
    items = [v.strip() for v in values if v.strip()]
    for item in items:
        err = next(iter(_item_validator().iter_errors(item)), None)
        if err is not None:
            raise ValueError(f"{PLANNED_TEST_CHANGES} item {item!r}: {err.message}")
    return items


def set_planned_test_changes(node: dict, raw_val: str) -> None:
    """One item per line; an empty value removes the field."""
    items = planned_test_change_items(raw_val.splitlines())
    if items:
        node[PLANNED_TEST_CHANGES] = items
    else:
        node.pop(PLANNED_TEST_CHANGES, None)
