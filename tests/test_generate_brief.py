"""Tests for generate_brief."""

from __future__ import annotations

import subprocess
import sys

from tests.helpers import BUNDLED_SCRIPTS, DOGFOOD, REPO, script_subprocess_env

import generate_brief as gb


def test_render_brief_m02_contains_title() -> None:
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.2", by_id)
    assert "Roadmap validator in CI" in text
    assert "M0.2" in text


def test_render_brief_dependencies_use_display_ids_not_raw_node_keys() -> None:
    """dependencies[] holds node_key UUIDs; brief must show peer display id + title."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M1", by_id)
    assert "## Dependencies (must complete first)" in text
    assert "M0.1" in text
    assert "Establish shared contracts and ADR skeleton" in text
    assert "- **44ef4a9d-" not in text


def test_unknown_node_exits() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(BUNDLED_SCRIPTS / "generate_brief.py"),
            "M999.9",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env=script_subprocess_env(),
    )
    assert proc.returncode != 0
