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


def test_validate_roadmap_yaml_line_limits_reads_config(tmp_path) -> None:
    """Threshold is read from constraints/file-limits.yaml; default is 500."""
    r = tmp_path / "roadmap"
    r.mkdir()
    (r / "roadmap.yaml").write_text(
        "version: 1\nincludes: [a.yaml]\n", encoding="utf-8"
    )
    # Two nodes so the single-node exception does not apply.
    node_block = (
        "nodes:\n"
        "  - id: M0\n    type: phase\n    title: x\n"
        "  - id: M1\n    parent_id: M0\n    type: milestone\n    title: y\n"
    )
    padding = "# pad\n" * 495  # 495 + 8 node lines = 503 > 500
    (r / "a.yaml").write_text(padding + node_block, encoding="utf-8")

    # Without a config the default is 500, so 501 lines should fail.
    with pytest.raises(SystemExit):
        rl.validate_roadmap_yaml_line_limits(tmp_path)

    # Raise the limit via config — should now pass.
    constraints = tmp_path / "constraints"
    constraints.mkdir()
    (constraints / "file-limits.yaml").write_text(
        "roadmap_yaml_max_lines: 600\n", encoding="utf-8"
    )
    rl.validate_roadmap_yaml_line_limits(tmp_path)  # must not raise


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
