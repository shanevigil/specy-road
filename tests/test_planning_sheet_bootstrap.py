from __future__ import annotations

from pathlib import Path


from specy_road.bundled_scripts.planning_sheet_bootstrap import (
    feature_sheet_level2_titles,
    gate_sheet_level2_titles,
    planning_review_expected_shape_block,
    render_feature_sheet_template,
    render_planning_sheet_template,
)


def test_render_feature_sheet_template_substitutes_node_id() -> None:
    text = render_feature_sheet_template("M9.9")
    assert "M9.9" not in text
    assert "{{NODE_ID}}" not in text


def test_feature_sheet_template_points_to_the_acceptance_checklist() -> None:
    tasks = render_feature_sheet_template("M9.9").split("## Tasks / checklist", 1)[1].split("## References", 1)[0]
    assert "acceptance criteria checklist (see `planning/README.md`)" in tasks
    assert "docs/roadmap-authoring.md" not in tasks
    doc = (Path(__file__).resolve().parents[1] / "specy_road" / "templates" / "project" / "planning" / "README.md").read_text(encoding="utf-8")
    checklist = doc.split("**Acceptance criteria checklist.**", 1)[1].split("\n", 1)[0]
    for item in ("state what is out of scope", "bound concurrency and input classes", "name the observable check"):
        assert item in checklist


def test_render_planning_sheet_template_gate_sections() -> None:
    text = render_planning_sheet_template("M0.1", node_type="gate")
    assert "M0.1" not in text
    assert "{{NODE_ID}}" not in text
    assert "Why this gate exists" in text
    assert "Criteria to clear" in text
    assert "Intent" not in text


def test_planning_review_expected_shape_block_gate() -> None:
    block = planning_review_expected_shape_block("gate")
    assert "gate planning sheet" in block
    assert "Why this gate exists" in block


def test_gate_sheet_level2_titles_match_template() -> None:
    titles = gate_sheet_level2_titles()
    assert titles == (
        "Why this gate exists",
        "Criteria to clear",
        "Decisions and notes",
        "Resolution",
        "References",
    )


def test_feature_sheet_level2_titles_match_scaffold_template() -> None:
    titles = feature_sheet_level2_titles()
    assert titles == (
        "Intent",
        "Approach",
        "Tasks / checklist",
        "References",
    )
