"""Tests for roadmap merge loading."""

from __future__ import annotations

import textwrap

import pytest

import roadmap_load as rl


def test_load_roadmap_merges_includes(tmp_path) -> None:
    r = tmp_path / "roadmap"
    r.mkdir()
    (r / "roadmap.yaml").write_text(
        textwrap.dedent(
            """\
            version: 1
            includes:
              - a.yaml
            """
        ),
        encoding="utf-8",
    )
    (r / "a.yaml").write_text(
        textwrap.dedent(
            """\
            nodes:
              - id: M0
                parent_id: null
                type: phase
            """
        ),
        encoding="utf-8",
    )
    doc = rl.load_roadmap(tmp_path)
    assert doc["version"] == 1
    assert len(doc["nodes"]) == 1
    assert doc["nodes"][0]["id"] == "M0"


def test_load_roadmap_rejects_mixing_nodes_and_includes(tmp_path) -> None:
    r = tmp_path / "roadmap"
    r.mkdir()
    (r / "roadmap.yaml").write_text(
        textwrap.dedent(
            """\
            version: 1
            includes: [a.yaml]
            nodes: []
            """
        ),
        encoding="utf-8",
    )
    (r / "a.yaml").write_text("nodes: []\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        rl.load_roadmap(tmp_path)
