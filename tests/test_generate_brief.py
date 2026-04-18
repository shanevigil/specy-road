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
    assert "## 1. Execution target" in text
    assert "## 2. Ancestor context chain" in text
    assert "## 7. Rollup semantics (reference)" in text


def test_render_brief_dependencies_use_display_ids_not_raw_node_keys() -> None:
    """dependencies[] holds node_key UUIDs; brief must show peer display id + title."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M1", by_id)
    assert "## 5. Dependencies (must complete first)" in text
    assert "M0.1" in text
    assert "Establish shared contracts and ADR skeleton" in text
    assert "- **44ef4a9d-" not in text


def test_render_brief_inlines_planning_sheet_body() -> None:
    """F-004: brief inlines the planning sheet content, not just paths."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    assert "## 3. Planning context (inlined)" in text
    # The dogfood M0.3 planning template contains the literal text "Intent".
    assert "## Intent" in text


def test_render_brief_inlines_shared_contracts() -> None:
    """F-004: brief inlines shared/*.md bodies in deterministic order."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    assert "## 4. Shared contracts (inlined, deterministic order)" in text
    # The dogfood ships a shared/api-contract.md.
    assert "shared/api-contract.md" in text


def test_render_brief_includes_touch_zone_instruction() -> None:
    """F-009: brief tells the implementer to derive/confirm touch zones."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    text = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    assert "## 6. Touch zones — implementing agent instruction" in text
    assert "TODO (DEV agent)" in text


def test_render_brief_is_deterministic() -> None:
    """F-004: same inputs => byte-identical output."""
    nodes = gb.load_nodes(DOGFOOD)
    by_id = gb.index(nodes)
    a = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    b = gb.render_brief("M0.3", by_id, repo_root=DOGFOOD)
    assert a == b


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
