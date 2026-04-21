"""Unit tests for brief_dependency_context (intent-only by default)."""

from __future__ import annotations

import sys
from pathlib import Path

from tests.helpers import BUNDLED_SCRIPTS  # noqa: E402

if str(BUNDLED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(BUNDLED_SCRIPTS))

from brief_dependency_context import (  # noqa: E402
    effective_dep_nodes,
    extract_intent_block,
    render_dependency_context_section,
)


_NK = "{tail:08d}-0000-4000-8000-000000000001"


def _node(
    nid: str,
    parent: str | None,
    *,
    type_: str = "task",
    title: str = "T",
    deps: list[str] | None = None,
    n_index: int = 1,
    planning_dir: str | None = None,
) -> dict:
    return {
        "id": nid,
        "node_key": _NK.format(tail=n_index),
        "parent_id": parent,
        "type": type_,
        "title": title,
        "dependencies": list(deps or []),
        "planning_dir": planning_dir,
    }


# ---------------------------------------------------------------------------
# extract_intent_block
# ---------------------------------------------------------------------------


def test_extract_intent_block_feature_sheet_returns_intent_body() -> None:
    text = (
        "## Intent\n"
        "\n"
        "Deliver an API for tasks.\n"
        "Supports CRUD.\n"
        "\n"
        "## Approach\n"
        "\n"
        "Build it.\n"
    )
    body = extract_intent_block(text, "task")
    assert body == "Deliver an API for tasks.\nSupports CRUD."


def test_extract_intent_block_gate_sheet_returns_why_block() -> None:
    text = (
        "## Why this gate exists\n"
        "\n"
        "Need legal sign-off before launch.\n"
        "\n"
        "## Criteria to clear\n"
        "\n"
        "- Approval letter on file.\n"
    )
    body = extract_intent_block(text, "gate")
    assert body == "Need legal sign-off before launch."


def test_extract_intent_block_missing_returns_none() -> None:
    text = "## Approach\n\nNo intent here.\n"
    assert extract_intent_block(text, "task") is None


def test_extract_intent_block_tolerates_case_and_trailing_whitespace() -> None:
    text = "##   intent  \n\nlowercased & padded.\n\n## Approach\n"
    body = extract_intent_block(text, "task")
    assert body == "lowercased & padded."


def test_extract_intent_block_tolerates_trailing_colon() -> None:
    text = "## Intent:\n\nWith a colon.\n"
    body = extract_intent_block(text, "task")
    assert body == "With a colon."


def test_extract_intent_block_only_first_match_wins() -> None:
    text = (
        "## Intent\n"
        "\n"
        "First.\n"
        "\n"
        "## Approach\n"
        "\n"
        "x\n"
        "\n"
        "## Intent\n"
        "\n"
        "Second.\n"
    )
    assert extract_intent_block(text, "task") == "First."


def test_extract_intent_block_skips_yaml_frontmatter() -> None:
    text = (
        "---\n"
        "id: M0.1\n"
        "---\n"
        "## Intent\n"
        "\n"
        "After frontmatter.\n"
    )
    assert extract_intent_block(text, "task") == "After frontmatter."


# ---------------------------------------------------------------------------
# effective_dep_nodes
# ---------------------------------------------------------------------------


def test_effective_dep_nodes_explicit_only() -> None:
    a = _node("M0.1", "M0", n_index=1)
    b = _node("M0.2", "M0", n_index=2, deps=[a["node_key"]])
    by_id = {a["id"]: a, b["id"]: b, "M0": _node("M0", None, type_="phase", n_index=99)}
    assert [d["id"] for d in effective_dep_nodes(b, by_id)] == ["M0.1"]


def test_effective_dep_nodes_inherits_from_ancestor() -> None:
    """A node inherits its ancestor's dependencies (effective dep set)."""
    a = _node("M0.1", "M0", n_index=1)
    phase = _node("M1", None, type_="phase", n_index=10, deps=[a["node_key"]])
    leaf = _node("M1.1", "M1", n_index=11)
    by_id = {n["id"]: n for n in (a, phase, leaf, _node("M0", None, type_="phase", n_index=99))}
    deps = effective_dep_nodes(leaf, by_id)
    assert [d["id"] for d in deps] == ["M0.1"]


def test_effective_dep_nodes_sorted_deterministically() -> None:
    a = _node("M0.10", "M0", n_index=10)
    b = _node("M0.2", "M0", n_index=2)
    c = _node("M0.1", "M0", n_index=1)
    target = _node(
        "M0.99", "M0", n_index=99,
        deps=[a["node_key"], b["node_key"], c["node_key"]],
    )
    by_id = {n["id"]: n for n in (a, b, c, target, _node("M0", None, type_="phase", n_index=999))}
    out = effective_dep_nodes(target, by_id)
    # Lexicographic sort by display id.
    assert [d["id"] for d in out] == ["M0.1", "M0.10", "M0.2"]


def test_effective_dep_nodes_returns_empty_when_no_node_key() -> None:
    n = {"id": "M9", "type": "task"}
    assert effective_dep_nodes(n, {"M9": n}) == []


# ---------------------------------------------------------------------------
# render_dependency_context_section
# ---------------------------------------------------------------------------


def test_render_dependency_context_no_deps_emits_explicit_marker(tmp_path: Path) -> None:
    n = _node("M0", None, type_="phase", n_index=1)
    lines = render_dependency_context_section(n, {"M0": n}, tmp_path)
    rendered = "\n".join(lines)
    assert "## 6. Dependency context (intent of upstream work)" in rendered
    assert "_no effective dependencies_" in rendered


def test_render_dependency_context_inlines_dep_intent(tmp_path: Path) -> None:
    """Happy path: dep has planning_dir on disk with a canonical Intent block."""
    pl = tmp_path / "planning"
    pl.mkdir()
    sheet_rel = "planning/M0.1_x_00000001-0000-4000-8000-000000000001.md"
    (tmp_path / sheet_rel).write_text(
        "## Intent\n\nDelivers shared contracts.\n\n## Approach\n\nx\n",
        encoding="utf-8",
    )
    a = _node("M0.1", "M0", n_index=1, planning_dir=sheet_rel, title="Bootstrap")
    target = _node("M0.2", "M0", n_index=2, deps=[a["node_key"]])
    by_id = {n["id"]: n for n in (a, target, _node("M0", None, type_="phase", n_index=99))}
    rendered = "\n".join(render_dependency_context_section(target, by_id, tmp_path))
    assert "### `M0.1` — Bootstrap" in rendered
    assert "**Intent (from this dependency's planning sheet):**" in rendered
    assert "Delivers shared contracts." in rendered
    # Approach must NOT leak into the brief (intent-only).
    assert "## Approach" not in rendered.split("### `M0.1`")[1].split("###", 1)[0]


def test_render_dependency_context_handles_missing_planning_dir(tmp_path: Path) -> None:
    a = _node("M0.1", "M0", n_index=1, planning_dir=None)
    target = _node("M0.2", "M0", n_index=2, deps=[a["node_key"]])
    by_id = {n["id"]: n for n in (a, target, _node("M0", None, type_="phase", n_index=99))}
    rendered = "\n".join(render_dependency_context_section(target, by_id, tmp_path))
    assert "no planning sheet" in rendered


def test_render_dependency_context_falls_back_when_intent_missing(tmp_path: Path) -> None:
    """Sheet exists but lacks ## Intent → emit fallback snippet from first lines."""
    pl = tmp_path / "planning"
    pl.mkdir()
    sheet_rel = "planning/M0.1_x_00000001-0000-4000-8000-000000000001.md"
    (tmp_path / sheet_rel).write_text(
        "## Approach\n\nfirst line of body.\nsecond line of body.\n",
        encoding="utf-8",
    )
    a = _node("M0.1", "M0", n_index=1, planning_dir=sheet_rel, title="Bootstrap")
    target = _node("M0.2", "M0", n_index=2, deps=[a["node_key"]])
    by_id = {n["id"]: n for n in (a, target, _node("M0", None, type_="phase", n_index=99))}
    rendered = "\n".join(render_dependency_context_section(target, by_id, tmp_path))
    assert "does not yet declare a canonical Intent section" in rendered
    assert "first line of body." in rendered
    assert "second line of body." in rendered


def test_render_dependency_context_is_byte_deterministic(tmp_path: Path) -> None:
    pl = tmp_path / "planning"
    pl.mkdir()
    sheet_rel = "planning/M0.1_x_00000001-0000-4000-8000-000000000001.md"
    (tmp_path / sheet_rel).write_text(
        "## Intent\n\nstable.\n", encoding="utf-8"
    )
    a = _node("M0.1", "M0", n_index=1, planning_dir=sheet_rel, title="Bootstrap")
    target = _node("M0.2", "M0", n_index=2, deps=[a["node_key"]])
    by_id = {n["id"]: n for n in (a, target, _node("M0", None, type_="phase", n_index=99))}
    a_render = render_dependency_context_section(target, by_id, tmp_path)
    b_render = render_dependency_context_section(target, by_id, tmp_path)
    assert a_render == b_render
