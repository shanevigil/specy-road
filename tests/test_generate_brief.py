"""Tests for generate_brief."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

import generate_brief as gb


def test_render_brief_m11_contains_title() -> None:
    nodes = gb.load_nodes()
    by_id = gb.index(nodes)
    text = gb.render_brief("M1.1", by_id)
    assert "Roadmap validator in CI" in text
    assert "M1.1" in text


def test_unknown_node_exits() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "generate_brief.py"),
            "M999.9",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
