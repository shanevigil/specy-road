"""F-011: scaffold ships a .gitignore that ignores session-scoped work files."""

from __future__ import annotations

from pathlib import Path

from specy_road.init_project import run_init_project


def test_init_project_ships_a_gitignore(tmp_path: Path) -> None:
    rc = run_init_project(tmp_path)
    assert rc == 0
    gi = tmp_path / ".gitignore"
    assert gi.is_file(), "init project should write a .gitignore"
    text = gi.read_text(encoding="utf-8")
    # Session-scoped files belong to the tool, not the team's history.
    assert "work/.on-complete-*.yaml" in text
    assert "work/prompt-*.md" in text
    assert "work/.milestone-session.yaml" in text
    # Briefs and impl-summaries are intentionally NOT ignored: the patterns
    # work/brief-*.md and work/implementation-summary-*.md must NOT appear
    # as their own lines (we still allow them in comments).
    non_comment = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert "work/brief-" not in non_comment
    assert "work/implementation-summary-" not in non_comment
