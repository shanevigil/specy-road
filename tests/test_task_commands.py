"""Tests for do_next_task and finish_task logic."""

from __future__ import annotations

from pathlib import Path

import pytest

import do_next_task as dnt
import finish_task as ft

# ---------------------------------------------------------------------------
# do_next_task: _available
# ---------------------------------------------------------------------------

_BASE_NODE = {
    "id": "M1.1",
    "type": "milestone",
    "title": "Example",
    "codename": "example",
    "execution_milestone": "Agentic-led",
    "status": "Not Started",
    "dependencies": [],
    "touch_zones": [],
}


def _reg(*node_ids: str) -> dict:
    return {
        "version": 1,
        "entries": [{"node_id": nid, "codename": nid} for nid in node_ids],
    }


def test_available_returns_unclaimed_agentic() -> None:
    nodes = [_BASE_NODE]
    result = dnt._available(nodes, _reg())
    assert len(result) == 1
    assert result[0]["id"] == "M1.1"


def test_available_excludes_claimed() -> None:
    nodes = [_BASE_NODE]
    assert dnt._available(nodes, _reg("M1.1")) == []


def test_available_excludes_complete() -> None:
    node = {**_BASE_NODE, "status": "Complete"}
    assert dnt._available([node], _reg()) == []


def test_available_excludes_unmet_deps() -> None:
    dep = {
        "id": "M1.0",
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "dependencies": [],
    }
    node = {**_BASE_NODE, "dependencies": ["M1.0"]}
    assert dnt._available([dep, node], _reg()) == []


def test_available_includes_when_deps_complete() -> None:
    dep = {
        "id": "M1.0",
        "type": "milestone",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Complete",
        "dependencies": [],
    }
    node = {**_BASE_NODE, "dependencies": ["M1.0"]}
    result = dnt._available([dep, node], _reg())
    assert len(result) == 1


def test_available_excludes_human_led_no_agentic_subtask() -> None:
    node = {**_BASE_NODE, "execution_milestone": "Human-led"}
    assert dnt._available([node], _reg()) == []


def test_available_includes_agentic_subtask() -> None:
    node = {
        **_BASE_NODE,
        "execution_milestone": None,
        "execution_subtask": "agentic",
    }
    result = dnt._available([node], _reg())
    assert len(result) == 1


def test_available_excludes_no_codename() -> None:
    node = {**_BASE_NODE, "codename": None}
    assert dnt._available([node], _reg()) == []


# ---------------------------------------------------------------------------
# finish_task: _patch_status
# ---------------------------------------------------------------------------

_CHUNK = """\
nodes:
  - id: M1.1
    parent_id: M1
    type: milestone
    title: "Example"
    codename: example
    execution_milestone: Agentic-led
    status: Not Started
    touch_zones: []
    dependencies: []

  - id: M1.2
    parent_id: M1
    type: milestone
    title: "Other"
    codename: other
    status: Not Started
"""


def test_patch_status_updates_correct_node() -> None:
    result, updated = ft._patch_status(_CHUNK, "M1.1", "Complete")
    assert updated
    assert "    status: Complete\n" in result
    # M1.2 must be untouched
    lines = result.splitlines()
    in_m12 = False
    for line in lines:
        if "- id: M1.2" in line:
            in_m12 = True
        if in_m12 and line.strip().startswith("status:"):
            assert "Not Started" in line
            break


def test_patch_status_unknown_id_returns_unchanged() -> None:
    result, updated = ft._patch_status(_CHUNK, "M9.9", "Complete")
    assert not updated
    assert result == _CHUNK


def test_patch_status_does_not_touch_nested_status() -> None:
    chunk = """\
nodes:
  - id: M1.1
    decision:
      status: pending
    status: Not Started
"""
    result, updated = ft._patch_status(chunk, "M1.1", "Complete")
    assert updated
    # decision.status untouched
    assert "      status: pending" in result
    # top-level status updated
    assert "    status: Complete" in result
